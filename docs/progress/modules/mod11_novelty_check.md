# mod11 · FineFilter · 逻辑新颖性检查

## 目标
把新候选因子与本地因子库中所有因子的 name/description/formula 对比，让 LLM 判断是否"实质等价"。

## 产出
- `src/tools/factor_library.py`
- 节点逻辑（合并到 `src/nodes/fine_filter.py`，M2 阶段先不拆三个文件）

## 与前后模块串联
- 上游：子图入口
- 下游：mod12 数据可得性检查（串行三关）；任一关失败 → mod14 Iterate

## 接口

```python
# src/tools/factor_library.py
class FactorLibrary:
    def __init__(self, index_path: Path):
        self.factors: list[FactorMeta] = self._load(index_path)

    def describe_for_llm(self) -> str:
        """拼成 LLM 可读的清单：id / name / logic_desc / formula。"""

@dataclass
class NoveltyCheckResult:
    passed: bool
    matched_factor_id: str | None
    reason: str
```

## 实现要点

### FactorMeta（读 factor_library_index.yaml）
```python
class FactorMeta(BaseModel):
    id: str
    name: str
    category: str
    logic_desc: str
    formula: str
    pit_note: str = ""
    values_path: str | None = None
```

### LLM Prompt
```
你在审核一个新因子是否与已有因子"实质等价"。
已有因子库：
{describe_for_llm()}

新候选因子：
- name: {c.name}
- logic_desc: {c.logic_desc}
- formula_draft: {c.formula_draft}

判断新候选是否与库中某个因子实质等价（同逻辑、同变量、仅参数/窗口不同也算等价）。
严格输出 JSON：
{"equivalent": bool, "matched_id": "<factor_id or null>", "reason": "..."}
```

### 判定规则
- `equivalent=True` → novelty 不通过，reason 里写"与 {matched_id} 实质等价"；
- `equivalent=False` → 通过。

## 验收标准
1. 把 c05（多周期加权行业动量）喂进去，应判与 `mom_20/mom_60` 等价；
2. 库中 24 个因子的描述正确加载；
3. LLM 返回非法 JSON 时有重试。

## 进度
⬜ 未开始
