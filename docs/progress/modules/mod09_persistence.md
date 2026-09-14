# mod09 · RunRecord 落盘

## 目标
每次节点结束时把当前 State 中的 candidates 序列化成 `data/runs/{run_id}/run_record.json`，支持断点续跑和事后审计。

## 产出
- `src/persistence.py`

## 与前后模块串联
- 上游：mod02（RunRecord 模型）
- 下游：mod08（图结束时调用 `finalize_run_record`）；M2 子图结束时也调用 `flush_candidate`

## 接口

```python
# src/persistence.py
from pathlib import Path
from .models import RunRecord, CandidateRecord, MaterialMeta

class RunRecorder:
    def __init__(self, run_id: str, cfg: AppConfig, material: MaterialMeta):
        self.run_dir = Path(cfg.persistence.run_root) / run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.record = RunRecord(
            run_id=run_id, material=material,
            started_at=datetime.now(),
            config_snapshot=cfg.model_dump(mode="json"),
        )

    def flush_candidate(self, c: CandidateRecord):
        """更新/插入一个候选，并整体写盘。"""
        ...

    def flush_all(self, candidates: list[CandidateRecord]):
        """粗筛后批量写。"""
        ...

    def finalize(self):
        """图结束：填 finished_at 和 summary。"""
        ...

    def path(self) -> Path:
        return self.run_dir / "run_record.json"
```

## 实现要点
- 每次 flush 整体重写 `run_record.json`（JSON 不大，简单可靠）；
- M1 阶段 summary 只统计 `total_extracted / coarse_passed / coarse_rejected`，其他字段先留 0；
- 同时把每个候选单独存一份 `candidates/{candidate_id}.json`，方便单候选重跑；
- 文件写盘用临时文件 + rename，避免写到一半进程被杀导致 JSON 损坏。

## 验收标准
1. 跑完一篇 PDF 后，`data/runs/{run_id}/run_record.json` 存在且是合法 JSON；
2. 文件中 candidates 数量与 State 中一致；
3. 进程中途 kill（模拟），最后一次 flush 的内容不丢；
4. `summary` 数字正确。

## 进度
⬜ 未开始
