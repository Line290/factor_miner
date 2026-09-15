"""MA2: AgentSessionState 消息模型、归约与校验。"""
from __future__ import annotations

from src.agent_state import (
    assistant_message,
    human_message,
    messages_token_estimate,
    tool_message,
    truncate_content,
    validate_tool_messages,
)


def test_message_constructors():
    assert human_message("hi") == {"role": "user", "content": "hi"}
    assert assistant_message("ok") == {"role": "assistant", "content": "ok"}
    tc = [{"id": "c1", "type": "function", "function": {"name": "f", "arguments": "{}"}}]
    assert assistant_message(tool_calls=tc)["tool_calls"] == tc
    assert assistant_message() == {"role": "assistant"}
    assert tool_message("c1", "out") == {"role": "tool", "tool_call_id": "c1", "content": "out"}


def test_messages_reducer_add_semantics():
    """模拟 LangGraph operator.add 归约：增量节点返回会拼接进 state.messages。"""
    initial: list[dict] = [human_message("a")]
    node_delta: list[dict] = [assistant_message("b")]
    state = {"messages": initial + node_delta}  # add reducer 的行为
    assert len(state["messages"]) == 2
    assert state["messages"][0]["role"] == "user"
    assert state["messages"][1]["role"] == "assistant"


def test_validate_tool_messages_ok():
    msgs = [
        assistant_message(tool_calls=[
            {"id": "c1", "type": "function", "function": {"name": "f", "arguments": "{}"}}
        ]),
        tool_message("c1", "result"),
    ]
    assert validate_tool_messages(msgs) == []


def test_validate_tool_messages_orphan_id():
    msgs = [tool_message("nope", "result")]
    problems = validate_tool_messages(msgs)
    assert len(problems) == 1
    assert "nope" in problems[0]


def test_validate_tool_messages_missing_id():
    msgs = [{"role": "tool", "content": "x"}]
    problems = validate_tool_messages(msgs)
    assert len(problems) == 1
    assert "缺少" in problems[0]


def test_validate_tool_messages_duplicate_consumption():
    msgs = [
        assistant_message(tool_calls=[
            {"id": "c1", "type": "function", "function": {"name": "f", "arguments": "{}"}}
        ]),
        tool_message("c1", "r1"),
        tool_message("c1", "r2"),
    ]
    problems = validate_tool_messages(msgs)
    assert any("重复消费" in p for p in problems)


def test_truncate_content_short_is_unchanged():
    assert truncate_content("abc", 10) == "abc"


def test_truncate_content_long_keeps_tail():
    out = truncate_content("A" * 100 + "TAIL", 20)
    assert len(out) <= 20
    assert out.endswith("TAIL")
    assert "已截断" in out


def test_truncate_content_edge_max_chars():
    out = truncate_content("12345", 5)
    assert out == "12345"


def test_messages_token_estimate():
    msgs = [human_message("你好世界"), assistant_message("好的")]
    est = messages_token_estimate(msgs)
    assert est >= 1
    assert isinstance(est, int)
