"""MA4: ReAct 主循环图测试（mock LLM：路由、循环、轮数保护）。"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from src.agent_graph import build_agent_graph
from src.agent_tools import tool_schemas
from src.config import AppConfig, load_config


class FakeLLM:
    """按预设序列返回 assistant message 的假 LLM。"""

    def __init__(self, responses: list[dict], summaries: list[str] | None = None):
        self.responses = list(responses)
        self.summaries = list(summaries or [])
        self.calls: list[list[dict]] = []
        self.call_kinds: list[str] = []

    def chat_message(self, messages, *, node=None, **kwargs):
        self.call_kinds.append("agent")
        self.calls.append(list(messages))
        if not self.responses:
            return {"role": "assistant", "content": "（默认结束）"}
        r = self.responses.pop(0)
        return dict(r)

    def chat_messages(self, messages, *, node=None, **kwargs):
        self.call_kinds.append(node or "chat_messages")
        self.calls.append(list(messages))
        if self.summaries:
            return self.summaries.pop(0)
        return "（默认摘要）"


def _tool_call_msg(name: str, args: dict | None = None, call_id: str = "c1") -> dict:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(args or {})},
            }
        ],
    }


def _build(cfg: AppConfig, llm, tmp_path: Path):
    # 隔离 checkpointer：临时目录覆盖 run_root，checkpoints.sqlite 落在其父目录
    cfg2 = cfg.model_copy(deep=True)
    cfg2.persistence.run_root = tmp_path / "runs"
    cfg2.agent.max_agent_rounds = 3
    return build_agent_graph(cfg2, llm)


def test_single_agent_then_finalize(tmp_path):
    cfg = load_config("configs/default.yaml")
    llm = FakeLLM([{"role": "assistant", "content": "完成，无工具需要"}])
    graph = _build(cfg, llm, tmp_path)

    out = graph.invoke(
        {"thread_id": "t1", "task": "分析材料"}, 
        config={"configurable": {"thread_id": "t1"}},
    )
    assert out["agent_rounds"] == 1
    assert out["final_answer"] == "完成，无工具需要"
    assert out.get("tool_calls_count", 0) == 0
    # 首轮自动注入 system 提示
    assert llm.calls[0][0]["role"] == "system"
    assert "Factor Miner Agent" in llm.calls[0][0]["content"]


def test_react_loop_with_tool_roundtrip(tmp_path):
    cfg = load_config("configs/default.yaml")
    llm = FakeLLM([
        _tool_call_msg("query_data_schema", {}, call_id="call_1"),
        {"role": "assistant", "content": "已查完数据字典，结论如下。"},
    ])
    graph = _build(cfg, llm, tmp_path)

    out = graph.invoke(
        {"thread_id": "t2", "task": "查数据字典"},
        config={"configurable": {"thread_id": "t2"}},
    )
    assert out["agent_rounds"] == 2
    assert out["tool_calls_count"] == 1
    assert out["final_answer"] == "已查完数据字典，结论如下。"

    roles = [m["role"] for m in out["messages"]]
    assert roles == ["system", "user", "assistant", "tool", "assistant"]
    tool_msg = out["messages"][-2]
    assert tool_msg["role"] == "tool"
    assert tool_msg["tool_call_id"] == "call_1"
    assert "可用字段" in tool_msg["content"]  # 真实工具结果回填


def test_max_rounds_guard_forces_finalize(tmp_path):
    cfg = load_config("configs/default.yaml")
    # LLM 无限循环返回 tool_calls
    llm = FakeLLM([
        _tool_call_msg("query_business_rules", {}, call_id=f"c{i}")
        for i in range(10)
    ])
    graph = _build(cfg, llm, tmp_path)

    out = graph.invoke(
        {"thread_id": "t3", "task": "无限循环测试"},
        config={"configurable": {"thread_id": "t3"}},
    )
    # 轮数上限 3 → 第 1、2 轮 tool_calls 已执行，第 3 轮被保护收尾（未执行）
    assert out["agent_rounds"] == 3
    assert out["tool_calls_count"] == 2
    assert out["final_answer"] == ""  # 没有最终答案，保护性收尾
    # 最后一条是第 3 轮 assistant 的 tool_calls（执行前被拦截）
    assert out["messages"][-1]["role"] == "assistant"
    assert out["messages"][-1].get("tool_calls")


def test_resume_from_checkpoint(tmp_path):
    cfg = load_config("configs/default.yaml")
    llm = FakeLLM([
        _tool_call_msg("query_data_schema", {}, call_id="call_r1"),
        {"role": "assistant", "content": "恢复后的最终答案"},
    ])
    graph = _build(cfg, llm, tmp_path)
    thread = {"configurable": {"thread_id": "t4"}}

    # 第一段：跑完第一轮（agent→tools）后中断（模拟），再恢复完整跑
    # 直接完整 invoke 验证 checkpointer 支持同一 thread 状态持久
    out = graph.invoke(
        {"thread_id": "t4", "task": "恢复测试"},
        config=thread,
    )
    assert out["agent_rounds"] == 2

    # 新图实例 + 同一 checkpointer 文件 → 相同 thread_id 应能看到历史状态
    llm2 = FakeLLM([])
    graph2 = _build(cfg, llm2, tmp_path)
    state = graph2.get_state(thread)
    assert state.values["thread_id"] == "t4"
    assert state.values["agent_rounds"] == 2


# ---------- MA7/MA8: token 预算监控与上下文压缩 ----------

def test_compress_triggers_and_replaces(tmp_path):
    cfg = load_config("configs/default.yaml")
    cfg2 = cfg.model_copy(deep=True)
    cfg2.persistence.run_root = tmp_path / "runs"
    cfg2.agent.max_agent_rounds = 10
    cfg2.agent.context_window_tokens = 200   # 极小窗口强制触发压缩
    cfg2.agent.messages_max_tokens_ratio = 0.6

    llm = FakeLLM(
        responses=[
            _tool_call_msg("query_business_rules", {}, call_id="c1"),
            _tool_call_msg("query_business_rules", {}, call_id="c2"),
            _tool_call_msg("query_business_rules", {}, call_id="c3"),
            _tool_call_msg("query_business_rules", {}, call_id="c4"),
            {"role": "assistant", "content": "最终结论"},
        ],
        summaries=["已压缩的历史摘要"],
    )
    graph = build_agent_graph(cfg2, llm)
    out = graph.invoke(
        {"thread_id": "t_comp", "task": "压缩测试"},
        config={"configurable": {"thread_id": "t_comp"}},
    )
    assert out["final_answer"] == "最终结论"
    assert "compress" in llm.call_kinds  # 压缩确实被触发

    msgs = out["messages"]
    # 首条仍是角色 system 提示
    assert msgs[0]["role"] == "system"
    # 存在 [历史会话摘要] 消息
    summary_msgs = [m for m in msgs if "[历史会话摘要]" in (m.get("content") or "")]
    assert len(summary_msgs) >= 1
    # 最近消息（含工具结果）保留原样
    assert any(m["role"] == "tool" for m in msgs[-6:])
    # 压缩后消息数显著减少（替换而非追加）
    assert len(msgs) < 10


def test_no_compress_within_budget(tmp_path):
    cfg = load_config("configs/default.yaml")
    cfg2 = cfg.model_copy(deep=True)
    cfg2.persistence.run_root = tmp_path / "runs"
    cfg2.agent.context_window_tokens = 131072  # 默认大窗口，短会话不触发

    llm = FakeLLM([
        _tool_call_msg("query_data_schema", {}, call_id="c1"),
        {"role": "assistant", "content": "完成"},
    ])
    graph = build_agent_graph(cfg2, llm)
    out = graph.invoke(
        {"thread_id": "t_nc", "task": "不压缩"},
        config={"configurable": {"thread_id": "t_nc"}},
    )
    assert "compress" not in llm.call_kinds
    assert out["final_answer"] == "完成"
