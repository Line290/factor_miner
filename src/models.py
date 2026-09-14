"""Pydantic data models shared across nodes and persisted to RunRecord."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, ConfigDict


class MaterialMeta(BaseModel):
    model_config = ConfigDict(validate_assignment=True)
    run_id: str
    path: str
    type: Literal["pdf", "json"]
    title: str | None = None
    pages: int | None = None
    loaded_at: datetime


CandidateStatus = Literal[
    "pending",
    "coarse_rejected",
    "fine_iter_failed",
    "code_fix_failed",
    "high_correlation",
    "code_runnable",
    "backtest_skipped",
    "backtest_failed",
    "backtested",
]


class IterationStep(BaseModel):
    """Snapshot of candidate state after each fine-filter round."""
    iteration: int          # 0 = original, 1 = after first iterate, ...
    motivation: str
    logic_desc: str
    formula_draft: str
    fine_checks: dict[str, Any] = Field(default_factory=dict)
    fine_feedback: str | None = None
    passed: bool = False
    timestamp: datetime


class CodeFixStep(BaseModel):
    """Snapshot of code execution / fix rounds."""
    round: int          # 0 = initial generation, 1 = after first fix, ...
    python_code: str
    success: bool
    error: str | None = None
    timestamp: datetime


class CandidateRecord(BaseModel):
    model_config = ConfigDict(validate_assignment=True)
    candidate_id: str
    name: str
    motivation: str
    logic_desc: str
    formula_draft: str
    source_page: int | None = None
    source_excerpt: str | None = None

    # Coarse
    coarse_scores: dict[str, float] = Field(default_factory=dict)
    coarse_avg: float | None = None
    coarse_passed: bool | None = None
    coarse_judgement: str | None = None

    # Fine (M2, placeholder in M1)
    fine_iteration: int = 0
    fine_checks: dict = Field(default_factory=dict)
    fine_passed: bool | None = None
    fine_feedback: str | None = None
    iteration_history: list[IterationStep] = Field(default_factory=list)

    # Code / values (M3/M4)
    formula_latex: str | None = None
    python_code: str | None = None
    required_fields: list[str] = Field(default_factory=list)
    code_fix_rounds: int = 0
    code_last_error: str | None = None
    code_runnable: bool | None = None
    code_fix_history: list[CodeFixStep] = Field(default_factory=list)
    factor_values_path: str | None = None
    corr_to_library: float | None = None
    corr_passed: bool | None = None
    backtest_report_path: str | None = None
    ic: float | None = None
    ir: float | None = None

    status: CandidateStatus = "pending"
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
