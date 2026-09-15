"""MA6: CLI run_agentic_session 测试（新会话 / resume / 错误分支，mock LLM）。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.config import load_config
from src.main import run_agentic_session
from src.session_store import SessionStore


class FakeLLM:
    def __init__(self, responses: list[dict]):
        self.responses = list(responses)
        self.calls: list[list[dict]] = []

    def chat_message(self, messages, *, node=None, **kwargs):
        self.calls.append(list(messages))
        if not self.responses:
            return {"role": "assistant", "content": "（默认结束）"}
        return dict(self.responses.pop(0))


def _cfg(tmp_path: Path):
    cfg = load_config("configs/default.yaml")
    cfg2 = cfg.model_copy(deep=True)
    cfg2.persistence.run_root = tmp_path / "runs"
    cfg2.persistence.session_store_path = tmp_path / "sessions.json"
    cfg2.agent.max_agent_rounds = 3
    return cfg2


def test_new_session_simple_answer(tmp_path):
    llm = FakeLLM([{"role": "assistant", "content": "任务完成。"}])
    out = run_agentic_session(_cfg(tmp_path), llm, task="简单任务")
    assert out["final_answer"] == "任务完成。"
    assert out["agent_rounds"] == 1

    store = SessionStore(_cfg(tmp_path).persistence.session_store_path)
    meta = store.get(out["thread_id"])
    assert meta is not None
    assert meta.status == "done"
    assert meta.task == "简单任务"


def test_new_session_requires_task(tmp_path):
    with pytest.raises(ValueError, match="--task"):
        run_agentic_session(_cfg(tmp_path), FakeLLM([]), task=None)


def test_resume_continues_existing_session(tmp_path):
    cfg = _cfg(tmp_path)
    # 第一次：一轮跑完
    out1 = run_agentic_session(cfg, FakeLLM([{"role": "assistant", "content": "第一轮"}]), task="任务A")
    sid = out1["thread_id"]

    # 第二次：resume 同一会话（mock 续答）
    llm2 = FakeLLM([{"role": "assistant", "content": "恢复后的补充回答"}])
    out2 = run_agentic_session(cfg, llm2, resume=sid)
    assert out2["thread_id"] == sid
    assert out2["final_answer"] == "恢复后的补充回答"

    meta = SessionStore(cfg.persistence.session_store_path).get(sid)
    assert meta.status == "done"
    assert meta.final_answer == "恢复后的补充回答"


def test_resume_unknown_session_raises(tmp_path):
    with pytest.raises(ValueError, match="会话不存在"):
        run_agentic_session(_cfg(tmp_path), FakeLLM([]), resume="no_such_session")


def test_material_injected_into_state(tmp_path, monkeypatch):
    # 造一个假的 JSON 材料
    mat_path = tmp_path / "roadshow.json"
    mat_path.write_text(json.dumps([
        {"speaker": "分析师", "content": "推荐动量因子方向。"}
    ]), encoding="utf-8")

    cfg = _cfg(tmp_path)
    llm = FakeLLM([{"role": "assistant", "content": "已读材料。"}])
    out = run_agentic_session(cfg, llm, task="读材料", material_path=str(mat_path))

    # 首轮 messages 应包含 material 注入（系统提示 + user + assistant）
    assert llm.calls[0][0]["role"] == "system"
    assert llm.calls[0][1]["role"] == "user"
    assert out["final_answer"] == "已读材料。"
    assert SessionStore(cfg.persistence.session_store_path).get(out["thread_id"]).material_path == str(mat_path)
