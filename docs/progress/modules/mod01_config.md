# mod01 · 配置加载与校验

## 目标
把 `configs/default.yaml` 加载成类型安全的 Python 对象，启动时校验必填项与路径。

## 产出
- `src/config.py`

## 与前后模块串联
- 上游：mod00（目录约定）
- 下游：所有节点 / LLM 客户端 / 持久化都从 `AppConfig` 读参数，不读环境变量或硬编码

## 接口

```python
# src/config.py
from pydantic import BaseModel, Field
from pathlib import Path

class LLMConfig(BaseModel):
    base_url: str
    api_key_env: str = "OPENAI_API_KEY"
    model: str
    temperature: float = 0.2
    timeout_sec: int = 120
    max_retries: int = 3
    overrides: dict[str, dict] = Field(default_factory=dict)

class ExtractionConfig(BaseModel):
    max_candidates_per_doc: int = 15
    min_candidates_per_doc: int = 1
    require_fields: list[str] = Field(default_factory=lambda: ["motivation","logic_desc","formula_draft"])

class CoarseDimension(BaseModel):
    key: str
    name: str
    desc: str

class CoarseConfig(BaseModel):
    dimensions: list[CoarseDimension]
    pass_threshold: float = 3.0
    min_dim_score: float = 2.0

class FineNoveltyConfig(BaseModel):
    enabled: bool = True
    top_k_for_llm: int = 0
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
    python_bin: str = ".venv/bin/python"
    pct_rules_path: Path

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
class BacktestAPIConfig(BaseModel):
    mode: str = "async"
    endpoint_submit: str
    endpoint_query: str
    poll_interval_sec: int = 5
    timeout_sec: int = 600
class BacktestConfig(BaseModel):
    enabled: bool = True
    mode: str = "local"
    local: BacktestLocalConfig
    api: BacktestAPIConfig

class PersistenceConfig(BaseModel):
    run_root: Path
    checkpointer: str = "sqlite"
    flush_each_node: bool = True

class RobustnessConfig(BaseModel):
    llm_retry: int = 3
    llm_retry_backoff_sec: list[int] = [2,5,10]
    json_repair: bool = True
    step_timeout_sec: int = 600

class AppConfig(BaseModel):
    llm: LLMConfig
    extraction: ExtractionConfig
    coarse_judge: CoarseConfig
    fine_filter: FineConfig
    code_generation: CodeGenConfig
    relevance: RelevanceConfig
    backtest: BacktestConfig
    persistence: PersistenceConfig
    robustness: RobustnessConfig

def load_config(path: str | Path = "configs/default.yaml") -> AppConfig:
    """读 YAML → pydantic 校验；相对路径以项目根为基准解析。"""
```

## 实现要点
- 路径字段在 pydantic validator 中统一转绝对路径（基于项目根）；
- 启动时检查 `data_schema_path`、`rules_path`、`pct_rules_path` 是否存在，不存在直接报错；
- `api_key_env` 字段只存环境变量名，真实 key 在 LLM 客户端里 `os.environ[api_key_env]`。

## 验收标准
1. `load_config()` 能正确加载 `configs/default.yaml`；
2. 故意把某个必填字段删掉，启动时报 pydantic 校验错误；
3. 路径字段全部解析为绝对路径。

## 进度
⬜ 未开始
