# mod14 · Iterate 节点

## 目标
LLM 根据细筛失败原因修改候选的 `motivation / logic_desc / formula_draft`，绕过失败检查，但不更换因子核心思想。

## 产出
- `src/nodes/iterate.py`

## 与前后模块串联
- 上游：FineFilter（任一关失败）
- 下游：回到 FineFilter 重新检查（回边）

## 接口

```python
# src/nodes/iterate.py
def iterate_node(state: PerCandidateState, *,
                  cfg: AppConfig, llm: LLMClient,
                  data_schema: DataSchema,
                  factor_library: FactorLibrary,
                  business_rules: BusinessRules) -> dict:
    """读 c.fine_feedback → LLM 改写 → 返回更新后的 candidate。"""
```

## 实现要点

### Prompt
```
你在迭代一个量化因子。原因子因以下原因未通过细筛：
{fine_feedback}

原因子：
- name: {c.name}
- motivation: {c.motivation}
- logic_desc: {c.logic_desc}
- formula_draft: {c.formula_draft}

可用数据字段：
{data_schema_summary}

业务规则：
{business_rules_summary}

要求：
1. 保留原因子的核心动机，不要换成另一个因子；
2. 只修改 logic_desc / formula_draft（必要时微调 motivation）；
3. 只能使用可用字段；
4. 不要违反业务规则；
5. 输出 JSON：{"name":..., "motivation":..., "logic_desc":..., "formula_draft":...}
```

### 路由
```python
def route_after_fine(state):
    c = state["candidate"]
    if c.fine_passed:
        return "generate_factor"   # M3
    if c.fine_iteration >= cfg.fine_filter.max_iterations:
        c.status = "fine_iter_failed"
        return "save"
    return "iterate"
```

Iterate 后 `fine_iteration += 1`，回到 FineFilter。

## 验收标准
1. 数据可得性失败时，LLM 改用可用字段；
2. 迭代 3 次后仍失败，状态置为 `fine_iter_failed`；
3. 核心动机不被换掉（LLM 输出的 motivation 与原 motivation 语义相近）。

## 进度
⬜ 未开始
