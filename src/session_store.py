"""MA5: Agentic session metadata store (threads).

以 JSON 文件持久化会话元数据（thread_id / 任务 / 材料 / 状态 / 统计 / 最终答案），
与 LangGraph checkpointer（消息快照，checkpoints.sqlite）互补：
- checkpointer 管"图执行状态"（可精确恢复到任意节点）；
- SessionStore 管"会话目录"（列表、任务摘要、恢复点），供 CLI --list-sessions / --resume。
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from loguru import logger


@dataclass
class SessionMeta:
    thread_id: str
    task: str
    material_path: str | None = None
    status: str = "active"          # active | done
    created_at: str = ""
    updated_at: str = ""
    agent_rounds: int = 0
    tool_calls_count: int = 0
    final_answer: str = ""

    def __post_init__(self):
        now = datetime.now().isoformat(timespec="seconds")
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now


class SessionStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._save({})

    # ---------- 读写 ----------

    def _load(self) -> dict:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, data: dict) -> None:
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    # ---------- 操作 ----------

    def create(self, thread_id: str, task: str, material_path: str | None = None) -> SessionMeta:
        data = self._load()
        if thread_id in data:
            raise ValueError(f"会话已存在: {thread_id}")
        meta = SessionMeta(
            thread_id=thread_id,
            task=task,
            material_path=material_path,
            status="active",
        )
        data[thread_id] = asdict(meta)
        self._save(data)
        logger.info(f"[session] created: {thread_id} task={task[:40]!r}")
        return meta

    def update(self, thread_id: str, **fields) -> SessionMeta:
        """更新任意字段并刷新 updated_at。"""
        data = self._load()
        if thread_id not in data:
            raise KeyError(f"会话不存在: {thread_id}")
        rec = data[thread_id]
        for k, v in fields.items():
            if k not in rec:
                raise KeyError(f"未知字段: {k}")
            rec[k] = v
        rec["updated_at"] = datetime.now().isoformat(timespec="seconds")
        data[thread_id] = rec
        self._save(data)
        return SessionMeta(**rec)

    def finalize(self, thread_id: str, *, final_answer: str, agent_rounds: int, tool_calls_count: int) -> SessionMeta:
        return self.update(
            thread_id,
            status="done",
            final_answer=final_answer,
            agent_rounds=agent_rounds,
            tool_calls_count=tool_calls_count,
        )

    def get(self, thread_id: str) -> SessionMeta | None:
        rec = self._load().get(thread_id)
        return SessionMeta(**rec) if rec else None

    def list_sessions(self, limit: int = 20) -> list[SessionMeta]:
        recs = self._load().values()
        metas = [SessionMeta(**r) for r in recs]
        metas.sort(key=lambda m: m.updated_at, reverse=True)
        return metas[:limit]

    def count(self) -> int:
        return len(self._load())
