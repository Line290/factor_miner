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
        """Multi-turn chat with explicit messages array."""
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

        # INFO 级可见进度：并行子图跑 LLM 时屏幕不再是死寂
        logger.info(f"LLM → node={node} model={model} msgs={len(messages)}")
        t0 = time.perf_counter()
        resp = self.client.chat.completions.create(**kwargs)
        content = resp.choices[0].message.content or ""
        logger.info(
            f"LLM ← node={node} {time.perf_counter() - t0:.1f}s "
            f"in={resp.usage.prompt_tokens if resp.usage else '?'} "
            f"out={resp.usage.completion_tokens if resp.usage else '?'}"
        )
        return content

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
