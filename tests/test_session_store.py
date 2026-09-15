"""MA5: SessionStore 会话元数据测试。"""
from __future__ import annotations

import pytest

from src.session_store import SessionStore


@pytest.fixture
def store(tmp_path):
    return SessionStore(tmp_path / "sessions.json")


def test_create_and_get(store):
    meta = store.create("s1", task="分析材料", material_path="data/reports/a.pdf")
    assert meta.thread_id == "s1"
    assert meta.status == "active"
    assert meta.created_at and meta.updated_at

    got = store.get("s1")
    assert got is not None
    assert got.task == "分析材料"
    assert got.material_path == "data/reports/a.pdf"


def test_create_duplicate_raises(store):
    store.create("s1", task="a")
    with pytest.raises(ValueError):
        store.create("s1", task="b")


def test_update_refreshes_timestamp(store):
    meta = store.create("s1", task="a")
    t0 = meta.updated_at
    updated = store.update("s1", agent_rounds=5)
    assert updated.agent_rounds == 5
    assert updated.updated_at >= t0


def test_finalize(store):
    store.create("s1", task="a")
    m = store.finalize("s1", final_answer="答案", agent_rounds=3, tool_calls_count=7)
    assert m.status == "done"
    assert m.final_answer == "答案"
    assert m.agent_rounds == 3
    assert m.tool_calls_count == 7
    assert store.get("s1").status == "done"


def test_list_sessions_sorted_by_updated_at(store):
    store.create("s1", task="先")
    store.create("s2", task="后")
    store.update("s1", agent_rounds=1)  # 刷新 s1 更新时间
    sessions = store.list_sessions()
    assert [s.thread_id for s in sessions] == ["s1", "s2"]


def test_list_sessions_limit(store):
    for i in range(5):
        store.create(f"s{i}", task=f"t{i}")
    assert len(store.list_sessions(limit=3)) == 3


def test_get_unknown_returns_none(store):
    assert store.get("nope") is None


def test_persistence_across_instances(tmp_path):
    p = tmp_path / "sessions.json"
    SessionStore(p).create("s1", task="a")
    # 新实例读取同一文件
    got = SessionStore(p).get("s1")
    assert got is not None and got.task == "a"
    assert SessionStore(p).count() == 1
