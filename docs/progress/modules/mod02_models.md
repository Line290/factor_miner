# mod02 · pydantic 数据模型

## 目标
定义业务层所有可序列化对象：`MaterialMeta` / `CandidateRecord` / `RunRecord`。这些对象既是节点间传递的载体，也是 RunRecord JSON 的 schema。

## 产出
- `src/models.py`

## 与前后模块串联
- 上游：mod01（配置类型不依赖）
- 下游：mod03（State 引用 CandidateRecord）、mod05/06/07（节点读写 CandidateRecord）、mod09（RunRecord 落盘）

## 接口

```python
# src/models.py
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Literal

class MaterialMeta(BaseModel):
    run_id: str
    path: str
    type: Literal["pdf", "json"]
    title: str | None = None
    pages: int | None = None
    loaded_at: datetime

class CandidateRecord(BaseModel):
    candidate_id: str
    name: str
    motivation: str
    logic_desc: str
    formula_draft: str
    source_page: int | None = None
    source_excerpt: str | None = None

    # 粗筛
    coarse_scores: dict[str, float] = Field(default_factory=dict)
    coarse_avg: float | None = None
    coarse_passed: bool | None = None
    coarse_judgement: str | None = None

    # 细筛（M2 才填，先占位）
    fine_iteration: int = 0
    fine_checks: dict = Field(default_factory=dict)
    fine_passed: bool | None = None
    fine_feedback: str | None = None

    # 代码 / 因子值（M3/M4 才填）
    formula_latex: str | None = None
    python_code: str | None = None
    required_fields: list[str] = Field(default_factory=list)
    code_fix_rounds: int = 0
    code_last_error: str | None = None
    code_runnable: bool | None = None
    factor_values_path: str | None = None
    corr_to_library: float | None = None
    corr_passed: bool | None = None
    backtest_report_path: str | None = None
    ic: float | None = None
    ir: float | None = None

    status: Literal[
        "pending", "coarse_rejected", "fine_iter_failed",
        "code_fix_failed", "high_correlation",
        "code_runnable", "backtested",
    ] = "pending"
    final_error: str | None = None

class RunSummary(BaseModel):
    total_extracted: int = 0
    coarse_passed: int = 0
    coarse_rejected: int = 0
    fine_passed: int = 0
    code_runnable: int = 0
    final_factors: int = 0

class RunRecord(BaseModel):
    run_id: str
    material: MaterialMeta
    started_at: datetime
    finished_at: datetime | None = None
    config_snapshot: dict = Field(default_factory=dict)
    candidates: list[CandidateRecord] = Field(default_factory=list)
    summary: RunSummary = Field(default_factory=RunSummary)
```

## 实现要点
- 所有模型用 pydantic v2；
- M1 阶段只用到 `pending / coarse_rejected` 两个 status，其他字段先定义不填；
- `config_snapshot` 是本次 run 用的配置的关键子集（模型名、阈值），便于复现。

## 验收标准
1. 能 `CandidateRecord(...)` 创建对象并 `model_dump_json()` 序列化；
2. 所有字段类型与技术文档 §10 一致；
3. RunRecord 能 round-trip（dump → load）不丢字段。

## 进度
⬜ 未开始
