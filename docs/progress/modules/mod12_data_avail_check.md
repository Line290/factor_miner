# mod12 · FineFilter · 数据可得性检查

## 目标
根据 `configs/data_schema.yaml` 判断候选因子所需的数据字段是否存在，或能否由已有字段推导。

## 产出
- `src/tools/data_schema.py`

## 与前后模块串联
- 上游：mod11 新颖性检查
- 下游：mod13 业务方向检查；失败 → mod14 Iterate

## 接口

```python
# src/tools/data_schema.py
@dataclass
class DataAvailResult:
    passed: bool
    required_fields: list[str]
    missing_fields: list[str]
    derivable_fields: list[str]
    reason: str

class DataSchema:
    def __init__(self, schema_path: Path):
        self.fields: dict[str, FieldMeta] = {}
        self.derived: list[DerivedField] = []
        self.unavailable: list[str] = []

    def check(self, required: list[str]) -> DataAvailResult:
        """逐个字段判断：直接命中 / 可推导 / 缺失。"""
```

## 实现要点

### 两步走
1. **LLM 抽字段**：让 LLM 从候选的 `logic_desc + formula_draft` 中列出它需要的原始数据字段（如 `close_adj, pe_ttm, float_shares`）；
2. **规则匹配**：Python 侧逐个字段查 data_schema：
   - 在 `fields` 里 → OK；
   - 在 `derived.formula` 里出现 → OK（标记为 derivable）；
   - 在 `unavailable` 里 → 缺失；
   - 都不在 → 缺失（LLM 可能用了未登记字段）。

### FieldMeta
```python
class FieldMeta(BaseModel):
    name: str
    dtype: str
    freq: str
    desc: str
    pit_note: str = ""
```

## 验收标准
1. 候选需要 `close_adj` → 通过；
2. 候选需要 `ret_5d` → 通过（derived）；
3. 候选需要 `industry_code` → LLM 判 fatal=true，直接失败不迭代；
4. 候选需要 `market_cap` → LLM 映射到 `total_mv`，通过；
5. 候选需要 `roe_ttm` → LLM 判 fatal=true（财务数据未接入）。

## 进度
✅ 已完成（2026-09-14）

**实现记录**：
- 初版：LLM 只抽字段名，代码精确匹配 → 问题：不同文档字段别名太多，unavailable 列表追不上
- 改进：LLM 一步判断（fields_needed / available / missing / fatal），代码兜底校验
- fatal 判断由 LLM 做：核心逻辑依赖整个大类数据（行业/财务）才 fatal，别名字段自动映射
- unavailable 列表只留大类说明（industry_data / financial_data），不枚举别名
