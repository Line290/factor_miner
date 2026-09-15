"""MA1 冒烟测试：qwen3.7-flash 真实工具调用闭环（消耗少量 token）。

用法:
    python scripts/smoke_tool_calls.py [--config configs/default.yaml]

验证内容:
    1. 第 1 轮 LLM 返回 tool_calls（id/name/arguments 原样透传）；
    2. 工具执行结果以 tool 消息回填，tool_call_id 严格匹配；
    3. 第 2 轮模型消费工具结果，给出最终答案（无工具或继续调用，≤3 轮收敛）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from loguru import logger

from src.agent_state import (
    assistant_message,
    human_message,
    tool_message,
    validate_tool_messages,
)
from src.config import load_config
from src.llm import LLMClient

# 内嵌测试工具（与项目领域解耦，仅验证工具调用链路）
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "add_numbers",
            "description": "计算两个数字之和",
            "parameters": {
                "type": "object",
                "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
                "required": ["a", "b"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_answer",
            "description": "返回一个固定的答案字符串 42",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


def _dispatch(name: str, args: dict) -> str:
    if name == "add_numbers":
        return json.dumps({"sum": args["a"] + args["b"]}, ensure_ascii=False)
    if name == "get_answer":
        return json.dumps({"answer": "42"}, ensure_ascii=False)
    return json.dumps({"error": f"unknown tool: {name}"}, ensure_ascii=False)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="configs/default.yaml")
    args = ap.parse_args()

    load_dotenv()
    logger.remove()
    logger.add(sys.stderr, level="INFO")

    cfg = load_config(args.config)
    llm = LLMClient(cfg.llm)

    messages = [human_message("请用工具计算 123 + 456，然后告诉我最终答案。")]
    final_content: str | None = None

    for round_idx in range(1, 4):
        print(f"\n== 第 {round_idx} 轮 ==")
        msg = llm.chat_message(messages, tools=TOOLS, temperature=0.0)

        if not msg.get("tool_calls"):
            final_content = msg.get("content") or ""
            print(f"最终回复: {final_content}")
            break

        print(f"tool_calls: {json.dumps(msg['tool_calls'], ensure_ascii=False)}")
        messages.append(assistant_message(tool_calls=msg["tool_calls"]))

        for tc in msg["tool_calls"]:
            fn = tc["function"]
            fn_args = json.loads(fn["arguments"] or "{}")
            out = _dispatch(fn["name"], fn_args)
            print(f"  执行 {fn['name']}({fn_args}) -> {out}")
            messages.append(tool_message(tc["id"], out))

        problems = validate_tool_messages(messages)
        if problems:
            print(f"FAIL: tool 消息校验失败: {problems}")
            return 1
    else:
        print("FAIL: 超过 3 轮仍未收敛")
        return 1

    if "579" not in (final_content or ""):
        print(f"FAIL: 最终答案未包含正确结果 579（got: {final_content!r}）")
        return 1

    print("\nPASS: qwen3.7-flash 工具调用闭环跑通（tool_calls 透传 + tool 消息回填 + 结果消费）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
