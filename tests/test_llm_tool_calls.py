"""MA1: LLMClient tool_calls 透传与流式接口（mock 响应，不依赖真实 API）。"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from openai.types.chat import (
    ChatCompletion,
    ChatCompletionChunk,
    ChatCompletionMessage,
    ChatCompletionMessageToolCall,
)
from openai.types.chat.chat_completion import Choice as CompletionChoice
from openai.types.chat.chat_completion_chunk import (
    Choice as ChunkChoice,
    ChoiceDelta,
    ChoiceDeltaToolCall,
    ChoiceDeltaToolCallFunction,
)
from openai.types.chat.chat_completion_message_tool_call import Function as ToolCallFunction

from src.config import LLMConfig
from src.llm import LLMClient


def _cfg() -> LLMConfig:
    return LLMConfig(
        base_url="http://mock.test",
        api_key_env="DASHSCOPE_API_KEY",
        model="test-model",
        temperature=0.0,
    )


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    return LLMClient(_cfg())


def _completion(message: ChatCompletionMessage) -> ChatCompletion:
    return ChatCompletion(
        id="chatcmpl-1",
        object="chat.completion",
        created=1,
        model="test-model",
        choices=[CompletionChoice(finish_reason="tool_calls", index=0, message=message)],
    )


def _chunk(content: str | None, tool_parts: list[tuple[str, str, str]] | None):
    """构造一个流式 chunk。

    tool_parts: [(id, name, arguments)]，name/arguments 为分片（可空字符串）。
    """
    tcs = None
    if tool_parts:
        tcs = [
            ChoiceDeltaToolCall(
                index=i,
                id=cid or None,
                function=ChoiceDeltaToolCallFunction(name=name or None, arguments=args),
            )
            for i, (cid, name, args) in enumerate(tool_parts)
        ]
    delta = ChoiceDelta(content=content, tool_calls=tcs)
    choice = ChunkChoice(delta=delta, finish_reason=None, index=0)
    return ChatCompletionChunk(
        id="chatcmpl-2",
        object="chat.completion.chunk",
        created=1,
        model="test-model",
        choices=[choice],
    )


def test_chat_message_returns_tool_calls(client):
    tool_call = ChatCompletionMessageToolCall(
        id="call_abc",
        type="function",
        function=ToolCallFunction(name="add_numbers", arguments='{"a": 1, "b": 2}'),
    )
    resp = _completion(ChatCompletionMessage(role="assistant", content=None, tool_calls=[tool_call]))

    with patch.object(client.client.chat.completions, "create", return_value=resp) as mock_create:
        out = client.chat_message(
            [{"role": "user", "content": "1+2=?"}],
            tools=[{"type": "function", "function": {"name": "add_numbers", "parameters": {}}}],
        )

    mock_create.assert_called_once()
    assert out["role"] == "assistant"
    assert out["tool_calls"][0]["id"] == "call_abc"
    assert out["tool_calls"][0]["function"]["name"] == "add_numbers"
    assert out["tool_calls"][0]["function"]["arguments"] == '{"a": 1, "b": 2}'


def test_chat_message_without_tools_returns_content(client):
    resp = _completion(ChatCompletionMessage(role="assistant", content="42"))
    with patch.object(client.client.chat.completions, "create", return_value=resp):
        out = client.chat_message([{"role": "user", "content": "hi"}])
    assert out["content"] == "42"
    assert "tool_calls" not in out


def test_chat_messages_legacy_returns_str(client):
    """旧接口 chat_messages 行为不变（返回 content 字符串）。"""
    resp = _completion(ChatCompletionMessage(role="assistant", content="42"))
    with patch.object(client.client.chat.completions, "create", return_value=resp):
        out = client.chat_messages([{"role": "user", "content": "hi"}])
    assert out == "42"
    assert isinstance(out, str)


def test_chat_stream_content_deltas(client):
    chunks = [_chunk("你", None), _chunk("好", None)]
    with patch.object(client.client.chat.completions, "create", return_value=iter(chunks)):
        deltas = list(client.chat_stream([{"role": "user", "content": "hi"}]))
    assert deltas == [
        {"type": "content", "content": "你"},
        {"type": "content", "content": "好"},
    ]


def test_chat_stream_tool_calls_deltas(client):
    chunks = [
        _chunk(None, [("call_1", "add_numb", '{"a')]),
        _chunk(None, [("call_1", "", ": 1}")]),
    ]
    with patch.object(client.client.chat.completions, "create", return_value=iter(chunks)):
        deltas = list(client.chat_stream([{"role": "user", "content": "hi"}], tools=[]))
    assert deltas[0]["type"] == "tool_calls"
    assert deltas[0]["id"] == "call_1"
    assert deltas[0]["name"] == "add_numb"
    assert deltas[0]["arguments"] == '{"a'
    assert deltas[1]["arguments"] == ": 1}"
