"""RunRecord persistence: write/flush run_record.json atomically."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

from loguru import logger

from .config import AppConfig
from .models import CandidateRecord, MaterialMeta, RunRecord, RunSummary


class RunRecorder:
    def __init__(self, run_id: str, cfg: AppConfig, material: MaterialMeta):
        self._init_common(run_id, cfg)
        self.record = RunRecord(
            run_id=run_id,
            material=material,
            started_at=datetime.now(),
            config_snapshot=cfg.model_dump(mode="json"),
        )
        self._flush()

    @classmethod
    def resume(cls, run_id: str, cfg: AppConfig) -> "RunRecorder":
        """从已有 run_record.json 重建 recorder，保留历史候选，不覆盖记录。

        resume 时 ingest 节点被跳过、holder 里没有 recorder，
        save/extract 等节点需要它续写已有记录。
        """
        obj = cls.__new__(cls)
        obj._init_common(run_id, cfg)
        record_path = obj.run_dir / "run_record.json"
        if record_path.exists():
            obj.record = RunRecord(**json.loads(record_path.read_text(encoding="utf-8")))
        else:
            logger.warning(f"resume: {record_path} 不存在，创建新的运行记录")
            obj.record = RunRecord(
                run_id=run_id,
                material=MaterialMeta(run_id=run_id, path="", type="json",
                                      loaded_at=datetime.now()),
                started_at=datetime.now(),
                config_snapshot=cfg.model_dump(mode="json"),
            )
        return obj

    def _init_common(self, run_id: str, cfg: AppConfig) -> None:
        self.run_id = run_id
        self.run_dir = Path(cfg.persistence.run_root) / run_id
        (self.run_dir / "candidates").mkdir(parents=True, exist_ok=True)
        (self.run_dir / "factors").mkdir(parents=True, exist_ok=True)
        (self.run_dir / "logs").mkdir(parents=True, exist_ok=True)

    def flush_candidate(self, c: CandidateRecord) -> None:
        """Insert or update one candidate, then flush the whole record."""
        existing = {x.candidate_id: i for i, x in enumerate(self.record.candidates)}
        if c.candidate_id in existing:
            self.record.candidates[existing[c.candidate_id]] = c
        else:
            self.record.candidates.append(c)

        # Also write per-candidate file
        cand_path = self.run_dir / "candidates" / f"{c.candidate_id}.json"
        cand_path.write_text(c.model_dump_json(indent=2), encoding="utf-8")
        self._flush()

    def flush_all(self, candidates: list[CandidateRecord]) -> None:
        """Replace the whole candidate list (used after coarse judge)."""
        self.record.candidates = list(candidates)
        for c in candidates:
            (self.run_dir / "candidates" / f"{c.candidate_id}.json").write_text(
                c.model_dump_json(indent=2), encoding="utf-8"
            )
        self._flush()

    def finalize(self) -> None:
        self.record.finished_at = datetime.now()
        passed = [c for c in self.record.candidates if c.coarse_passed]
        rejected = [c for c in self.record.candidates if c.status == "coarse_rejected"]
        self.record.summary = RunSummary(
            total_extracted=len(self.record.candidates),
            coarse_passed=len(passed),
            coarse_rejected=len(rejected),
            fine_passed=sum(1 for c in self.record.candidates if c.fine_passed),
            code_runnable=sum(1 for c in self.record.candidates if c.code_runnable),
            final_factors=sum(
                1 for c in self.record.candidates if c.status in ("code_runnable", "backtested")
            ),
        )
        self._flush()
        logger.info(f"Run {self.run_id} finalized at {self.run_dir}")

    def _flush(self) -> None:
        target = self.run_dir / "run_record.json"
        # Atomic write: temp file in same dir + rename
        fd, tmp = tempfile.mkstemp(dir=self.run_dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(self.record.model_dump_json(indent=2))
            os.replace(tmp, target)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def path(self) -> Path:
        return self.run_dir / "run_record.json"
