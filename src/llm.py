"""OpenAI-compatible LLM client with retry and JSON parsing."""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any

from loguru import logger
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from .config import LLMConfig


def _log_retry(retry_state) -> None:
    logger.warning(
        f"LLM 调用第 {retry_state.attempt_number} 次尝试失败: "
        f"{retry_state.outcome.exception()}; "
        f"{retry_state.next_action.sleep:.1f}s 后重试"
    )


class LLMClient:
    def __init__(self, cfg: LLMConfig):
        self.cfg = cfg
        api_key = os.environ.get(cfg.api_key_env)
        if not api_key:
            raise RuntimeError(
                f"Environment variable {cfg.api_key_env} is not set. "
                "Please export it before running."
            )
        # max_retries=0: 关闭 SDK 隐形重试，tenacity 是唯一重试层（有日志可见），
        # 否则两层叠加最坏 3×3=9 次请求 ≈ 18 分钟才报错
        self.client = OpenAI(base_url=cfg.base_url, api_key=api_key,
                             timeout=cfg.timeout_sec, max_retries=0)

    def _resolve_model(self, node: str | None) -> str:
        if node and node in self.cfg.overrides:
            return self.cfg.overrides[node].get("model", self.cfg.model)
        return self.cfg.model

    def chat(
        self,
        system: str,
        user: str,
        *,
        node: str | None = None,
        temperature: float | None = None,
        json_mode: bool = False,
    ) -> str:
        return self.chat_messages(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            node=node,
            temperature=temperature,
            json_mode=json_mode,
        )

    def _build_kwargs(
        self,
        messages: list[dict],
        *,
        node: str | None,
        temperature: float | None,
        json_mode: bool,
        tools: list[dict] | None,
        tool_choice: str,
    ) -> dict[str, Any]:
        model = self._resolve_model(node)
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.cfg.temperature,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice
        return kwargs

    def _log_call(self, node: str | None, model: str, messages: list[dict]) -> None:
        # INFO 级可见进度：并行子图跑 LLM 时屏幕不再是死寂
        logger.info(f"LLM → node={node} model={model} msgs={len(messages)}")

    @staticmethod
    def _log_response(node: str | None, t0: float, resp) -> None:
        logger.info(
            f"LLM ← node={node} {time.perf_counter() - t0:.1f}s "
            f"in={resp.usage.prompt_tokens if resp.usage else '?'} "
            f"out={resp.usage.completion_tokens if resp.usage else '?'}"
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
        before_sleep=_log_retry,
    )
    def chat_messages(
        self,
        messages: list[dict],
        *,
        node: str | None = None,
        temperature: float | None = None,
        json_mode: bool = False,
        tools: list[dict] | None = None,
        tool_choice: str = "auto",
    ) -> str:
        """Multi-turn chat with explicit messages array.

        返回 content 字符串（旧流水线节点兼容接口）；
        需要完整 message（含 tool_calls）请用 :meth:`chat_message`。
        """
        model = self._resolve_model(node)
        kwargs = self._build_kwargs(
            messages, node=node, temperature=temperature,
            json_mode=json_mode, tools=tools, tool_choice=tool_choice,
        )
        self._log_call(node, model, messages)
        t0 = time.perf_counter()
        resp = self.client.chat.completions.create(**kwargs)
        content = resp.choices[0].message.content or ""
        self._log_response(node, t0, resp)
        return content

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
        before_sleep=_log_retry,
    )
    def chat_message(
        self,
        messages: list[dict],
        *,
        node: str | None = None,
        temperature: float | None = None,
        json_mode: bool = False,
        tools: list[dict] | None = None,
        tool_choice: str = "auto",
    ) -> dict:
        """Multi-turn chat returning the full assistant message dict.

        供 Agentic 会话层使用：返回 OpenAI 原生 assistant message，
        ``tool_calls`` 原样透传（id / name / arguments），可直接回填消息栈；
        模型未调用工具时返回体不含 ``tool_calls`` 字段。
        """
        model = self._resolve_model(node)
        kwargs = self._build_kwargs(
            messages, node=node, temperature=temperature,
            json_mode=json_mode, tools=tools, tool_choice=tool_choice,
        )
        self._log_call(node, model, messages)
        t0 = time.perf_counter()
        resp = self.client.chat.completions.create(**kwargs)
        self._log_response(node, t0, resp)
        return resp.choices[0].message.model_dump(exclude_none=True)

    def chat_stream(
        self,
        messages: list[dict],
        *,
        node: str | None = None,
        temperature: float | None = None,
        tools: list[dict] | None = None,
        tool_choice: str = "auto",
    ):
        """Stream chat completions, yielding delta dicts.

        ``yield`` 两种增量：
        - ``{"type": "content", "content": str}``：文本增量
        - ``{"type": "tool_calls", "id": str|None, "name": str|None, "arguments": str}``：
          工具调用增量（arguments 是分片 JSON 字符串，需自行拼接）

        注意：生成器惰性求值，tenacity 重试不适用；调用方自行处理流中断。
        """
        model = self._resolve_model(node)
        kwargs = self._build_kwargs(
            messages, node=node, temperature=temperature,
            json_mode=False, tools=tools, tool_choice=tool_choice,
        )
        self._log_call(node, model, messages)
        t0 = time.perf_counter()
        stream = self.client.chat.completions.create(**kwargs, stream=True)
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta.content:
                yield {"type": "content", "content": delta.content}
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    yield {
                        "type": "tool_calls",
                        "id": tc.id,
                        "name": tc.function.name if tc.function else None,
                        "arguments": tc.function.arguments if tc.function else "",
                    }
        logger.info(f"LLM stream ← node={node} {time.perf_counter() - t0:.1f}s done")

    def chat_json(
        self,
        system: str,
        user: str,
        *,
        node: str | None = None,
    ) -> dict:
        """Chat with JSON mode, with tolerant parsing and one retry."""
        raw = self.chat(system, user, node=node, json_mode=True)
        try:
            return self._parse_json(raw)
        except Exception as e:
            logger.warning(f"First JSON parse failed: {e}; retrying with stricter prompt.")
            user2 = user + "\n\n[系统提示] 上次输出不是合法 JSON，请只输出 JSON 对象，不要任何解释或 markdown 代码块。"
            raw2 = self.chat(system, user2, node=node, json_mode=True)
            return self._parse_json(raw2)

    @staticmethod
    def _parse_json(text: str) -> dict:
        text = text.strip()
        # Strip ```json ... ``` fences if present
        m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
        if m:
            text = m.group(1).strip()
        # Try direct parse
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            # Try to find the first {...} block
            start = text.find("{")
            end = text.rfind("}")
            if start == -1 or end == -1 or end <= start:
                # Last resort: json_repair
                from json_repair import repair_json
                obj = json.loads(repair_json(text))
            else:
                try:
                    obj = json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    from json_repair import repair_json
                    obj = json.loads(repair_json(text[start : end + 1]))
        if not isinstance(obj, dict):
            raise ValueError(f"Expected JSON object, got {type(obj).__name__}")
        return obj
