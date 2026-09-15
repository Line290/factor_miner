"""Configuration loading and validation."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

# Project root = parent of src/
PROJECT_ROOT = Path(__file__).resolve().parent.parent


class LLMConfig(BaseModel):
    provider: str = "openai_compatible"
    base_url: str
    api_key_env: str = "OPENAI_API_KEY"
    model: str
    temperature: float = 0.2
    timeout_sec: int = 120
    max_retries: int = 3
    overrides: dict[str, dict[str, Any]] = Field(default_factory=dict)


class ExtractionConfig(BaseModel):
    max_candidates_per_doc: int = 15
    min_candidates_per_doc: int = 1
    require_fields: list[str] = Field(
        default_factory=lambda: ["motivation", "logic_desc", "formula_draft"]
    )


class CoarseDimension(BaseModel):
    key: str
    name: str
    desc: str


class CoarseConfig(BaseModel):
    dimensions: list[CoarseDimension]
    pass_threshold: float = 3.0
    min_dim_score: float = 2.0
    fail_action: str = "mark_and_archive"


class FineNoveltyConfig(BaseModel):
    enabled: bool = True
    top_k_for_llm: int = 0
    llm_judge_threshold: str = "equivalent"


class FineDataConfig(BaseModel):
    enabled: bool = True
    data_schema_path: Path
    allow_derived_fields: bool = True


class FineBizConfig(BaseModel):
    enabled: bool = True
    rules_path: Path


class FineConfig(BaseModel):
    max_iterations: int = 3
    novelty_check: FineNoveltyConfig
    data_availability: FineDataConfig
    business_rules: FineBizConfig


class CodeGenConfig(BaseModel):
    max_fix_rounds: int = 10
    sandbox_timeout_sec: int = 60
    sandbox_memory_mb: int = 2048
    python_bin: str = "~/miniconda3/envs/factor-calc/bin/python"
    pct_rules_path: Path

    @field_validator("python_bin")
    @classmethod
    def _expand_python_bin(cls, v: str) -> str:
        # 支持 ~/ 开头和相对路径
        return os.path.expanduser(v)


class RelevanceConfig(BaseModel):
    enabled: bool = True
    corr_method: str = "spearman"
    max_corr_to_library: float = 0.7
    lookback_days: int = 250


class BacktestLocalConfig(BaseModel):
    backend: str = "alphalens-reloaded"
    universe: list[str] = Field(default_factory=lambda: ["csi800"])
    start_date: str = "2019-01-01"
    end_date: str = "auto"
    min_list_days: int = 252


class BacktestAPIConfig(BaseModel):
    mode: str = "async"
    endpoint_submit: str = ""
    endpoint_query: str = ""
    poll_interval_sec: int = 5
    timeout_sec: int = 600


class AutoArchiveConfig(BaseModel):
    enabled: bool = True
    min_ic: float = 0.03
    min_ir: float = 0.3


class BacktestConfig(BaseModel):
    enabled: bool = True
    mode: str = "local"
    local: BacktestLocalConfig
    auto_archive: AutoArchiveConfig = AutoArchiveConfig()
    api: BacktestAPIConfig


class PersistenceConfig(BaseModel):
    run_root: Path
    checkpointer: str = "sqlite"
    flush_each_node: bool = True


class RobustnessConfig(BaseModel):
    llm_retry: int = 3
    llm_retry_backoff_sec: list[int] = [2, 5, 10]
    json_repair: bool = True
    step_timeout_sec: int = 600
    max_concurrency: int = 5   # 并行跑多少个子图（候选因子）


class AgentConfig(BaseModel):
    """Agentic 会话模式（Claude Code 式 ReAct 循环）配置。"""
    max_agent_rounds: int = 30          # agent 节点最大执行轮数（防 LLM 死循环）
    tool_output_truncate_chars: int = 8000   # 单条工具输出截断上限
    messages_max_tokens_ratio: float = 0.6   # 消息栈 token 预算 = 模型窗口 × 该比例（触发压缩）
    human_in_the_loop: bool = False     # 高风险工具调用前人工确认（默认全自动）


class AppConfig(BaseModel):
    llm: LLMConfig
    extraction: ExtractionConfig = Field(default_factory=ExtractionConfig)
    coarse_judge: CoarseConfig
    fine_filter: FineConfig
    code_generation: CodeGenConfig
    relevance: RelevanceConfig = Field(default_factory=RelevanceConfig)
    backtest: BacktestConfig
    persistence: PersistenceConfig
    robustness: RobustnessConfig = Field(default_factory=RobustnessConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)

    @model_validator(mode="after")
    def _check_paths(self) -> "AppConfig":
        for p in [
            self.fine_filter.data_availability.data_schema_path,
            self.fine_filter.business_rules.rules_path,
            self.code_generation.pct_rules_path,
        ]:
            if not p.exists():
                raise FileNotFoundError(f"Configured path does not exist: {p}")
        return self


def _resolve(p: Path | str) -> Path:
    path = Path(p)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def load_config(path: str | Path = "configs/default.yaml") -> AppConfig:
    """Load YAML config and validate. Relative paths resolved against project root."""
    cfg_path = _resolve(path)
    with open(cfg_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    # Resolve relative paths inside the config file to absolute.
    raw["fine_filter"]["data_availability"]["data_schema_path"] = str(
        _resolve(raw["fine_filter"]["data_availability"]["data_schema_path"])
    )
    raw["fine_filter"]["business_rules"]["rules_path"] = str(
        _resolve(raw["fine_filter"]["business_rules"]["rules_path"])
    )
    raw["code_generation"]["pct_rules_path"] = str(
        _resolve(raw["code_generation"]["pct_rules_path"])
    )
    raw["persistence"]["run_root"] = str(_resolve(raw["persistence"]["run_root"]))

    return AppConfig.model_validate(raw)
