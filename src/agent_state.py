"""Agent session state and message helpers (Claude Code-style ReAct loop)."""
from __future__ import annotations

from datetime import datetime
from operator import add
from typing import Annotated, Any, TypedDict

from .models import CandidateRecord


class AgentSessionState(TypedDict, total=False):
    """State for the agentic session graph (ReAct loop).

    ``messages`` 是 OpenAI Chat Completions 原生 dict 列表
    （role: user / assistant / tool），用 ``operator.add`` 归约以支持节点增量返回。
    """

    # 会话元数据
    thread_id: str
    task: str                      # 用户本轮任务描述
    material_path: str | None      # 可选输入材料（研报/论文/纪要）

    # ReAct 消息栈
    messages: Annotated[list[dict], add]

    # 终止保护与计数
    agent_rounds: int              # agent 节点已执行轮数（上限见配置）
    tool_calls_count: int          # 累计工具调用次数

    # 因子挖掘产出（finalize 阶段回填）
    candidates: list[CandidateRecord]

    # 错误收集
    errors: Annotated[list[str], add]
    started_at: datetime
    finished_at: datetime


# ---------- 消息构造 ----------

def human_message(content: str) -> dict:
    """构造 user 消息。"""
    return {"role": "user", "content": content}


def assistant_message(content: str | None = None, tool_calls: list[dict] | None = None) -> dict:
    """构造 assistant 消息。

    ``tool_calls`` 为 OpenAI 原生格式：
    ``[{"id": str, "type": "function", "function": {"name": str, "arguments": str}}]``
    """
    msg: dict = {"role": "assistant"}
    if content is not None:
        msg["content"] = content
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return msg


def tool_message(tool_call_id: str, content: str) -> dict:
    """构造 tool 消息。

    ``tool_call_id`` 必须与 assistant 消息中 ``tool_calls[i]["id"]`` 原样一致，
    否则 qwen / OpenAI 兼容接口会报错。
    """
    return {"role": "tool", "tool_call_id": tool_call_id, "content": content}


# ---------- 消息校验与工具函数 ----------

def collect_pending_tool_call_ids(messages: list[dict]) -> set[str]:
    """从消息栈中收集所有 assistant 消息声明过的 tool_call id。

    用于校验 tool 消息的 ``tool_call_id`` 都有对应的调用声明。
    """
    ids: set[str] = set()
    for m in messages:
        if m.get("role") != "assistant":
            continue
        for tc in m.get("tool_calls", []) or []:
            if tc.get("id"):
                ids.add(tc["id"])
    return ids


def validate_tool_messages(messages: list[dict]) -> list[str]:
    """校验消息栈中的 tool 消息引用完整性。

    返回问题列表；空列表 = 全部合法。规则：
    1. tool 消息必须携带 ``tool_call_id``；
    2. 该 id 必须能在消息栈中找到对应的 assistant tool_calls 声明；
    3. assistant 声明的每个 id 最多被一个 tool 消息消费。
    """
    pending = collect_pending_tool_call_ids(messages)
    consumed: set[str] = set()
    problems: list[str] = []
    for i, m in enumerate(messages):
        if m.get("role") != "tool":
            continue
        tid = m.get("tool_call_id")
        if not tid:
            problems.append(f"messages[{i}]: tool 消息缺少 tool_call_id")
            continue
        if tid not in pending:
            problems.append(f"messages[{i}]: tool_call_id={tid!r} 无对应 assistant tool_calls 声明")
            continue
        if tid in consumed:
            problems.append(f"messages[{i}]: tool_call_id={tid!r} 被重复消费")
        consumed.add(tid)
    return problems


def truncate_content(text: str, max_chars: int, tail: str = "\n…[已截断]") -> str:
    """按字符截断工具输出/长文本，防止撑爆上下文。

    仅截断中段，保留开头与结尾各一半，避免丢失末尾关键信息（如报错堆栈）。
    """
    if len(text) <= max_chars:
        return text
    half = (max_chars - len(tail)) // 2
    return text[:half] + tail + text[-half:]


def last_assistant_message(messages: list[dict]) -> dict | None:
    """返回消息栈中最后一条 assistant 消息（含 tool_calls 的那条）。"""
    for m in reversed(messages):
        if m.get("role") == "assistant":
            return m
    return None


def last_tool_calls(messages: list[dict]) -> list[dict]:
    """返回最后一条 assistant 消息声明的 tool_calls（空列表 = 无）。"""
    last = last_assistant_message(messages)
    if last is None:
        return []
    return last.get("tool_calls") or []


def messages_token_estimate(messages: list[dict], chars_per_token: float = 3.0) -> int:
    """粗略估算消息栈 token 数（中文场景约 1 token ≈ 1.5~3 字符）。

    仅用于触发上下文压缩的粗粒度预算，精确值以模型 usage 为准。
    """
    total_chars = 0
    for m in messages:
        content = m.get("content") or ""
        if isinstance(content, list):
            # OpenAI 多段 content（少见），按文本段估算
            total_chars += sum(
                len(seg.get("text") or "") for seg in content if isinstance(seg, dict)
            )
        else:
            total_chars += len(str(content))
        if m.get("role") == "assistant":
            for tc in m.get("tool_calls", []) or []:
                fn = tc.get("function", {})
                total_chars += len(fn.get("name") or "") + len(fn.get("arguments") or "")
    return max(1, int(total_chars / chars_per_token))
