# mod13 · FineFilter · 业务方向检查

## 目标
按 `configs/business_rules.yaml` 判断候选因子是否违反业务黑名单（高频 T0 / ST / 次新股等）。

## 产出
- `src/tools/business_rule.py`

## 与前后模块串联
- 上游：mod12 数据可得性检查
- 下游：三关全过 → GenerateFactor（M3）；任一失败 → mod14 Iterate

## 接口

```python
# src/tools/business_rule.py
@dataclass
class BizCheckResult:
    passed: bool
    violated: list[str]   # rule_id 列表
    reason: str

class BusinessRules:
    def __init__(self, rules_path: Path):
        self.rules: list[Rule] = self._load(rules_path)

    def check(self, candidate: CandidateRecord, llm: LLMClient) -> BizCheckResult:
        """keyword 初筛 + LLM 语义判断。"""
```

## 实现要点

### Rule
```python
class Rule(BaseModel):
    id: str
    name: str
    type: str            # keyword | semantic
    desc: str
    match_keywords: list[str] = []
    severity: str = "hard"
```

### 判断流程
1. **keyword 类**：直接在 `logic_desc + formula_draft` 中搜 `match_keywords`，命中即违反；
2. **semantic 类**：把候选描述 + 规则清单喂给 LLM，问"是否违反规则 X"；
3. 任一 hard 规则违反 → `passed=False`。

## 验收标准
1. 候选描述含"T+0" → 违反 no_high_freq_t0；
2. 候选未提 ST/次新股 → 通过；
3. LLM 判断"持仓周期 5 日"不算 T0 → 通过。

## 进度
⬜ 未开始
