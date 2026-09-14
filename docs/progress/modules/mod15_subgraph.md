# mod15 · 子图组装与主图 Send 扇出

## 目标
把 FineFilter / Iterate 组装成 PerCandidateSubgraph，并改造主图的 `route_after_coarse` 用 `Send` 扇出。

## 产出
- `src/graph.py`（改造）
- `src/nodes/fine_filter.py`（三关合一节点）

## 与前后模块串联
- 上游：主图 CoarseJudge
- 下游：子图结束 → M3 GenerateFactor（M2 阶段先打日志占位）

## 接口

```python
# 主图改造
from langgraph.types import Send

def route_after_coarse(state):
    passed = [c for c in state["candidates"] if c.coarse_passed]
    return [
        Send("per_candidate_subgraph", {
            "candidate": c.model_dump(),
            "run_id": state["run_id"],
        })
        for c in passed
    ]

# 子图
def build_per_candidate_subgraph(cfg, llm, recorder,
                                  factor_library, data_schema, business_rules):
    g = StateGraph(PerCandidateState)
    g.add_node("fine_filter", ...)
    g.add_node("iterate", ...)
    g.add_node("save", ...)
    g.set_entry_point("fine_filter")
    g.add_conditional_edges("fine_filter", route_after_fine, {
        "generate_factor": "save",     # M2 占位，M3 改成真节点
        "iterate": "iterate",
        "save": "save",
    })
    g.add_edge("iterate", "fine_filter")
    g.add_edge("save", END)
    return g.compile()
```

## 实现要点
- 主图通过 `Send` 把每个通过粗筛的候选投递到子图；
- 子图的 `save` 节点把最终 CandidateRecord flush 到 RunRecord；
- M2 阶段 `generate_factor` 边先指向 `save`（占位），M3 再接真节点；
- 子图节点通过闭包拿 cfg/llm/recorder/factor_library 等。

## 验收标准
1. 一篇材料有 2 个候选通过粗筛 → 子图跑 2 次（并行或串行均可）；
2. 每个候选的 fine_checks 结果写入 RunRecord；
3. 迭代失败的候选状态为 `fine_iter_failed`；
4. 主图聚合后 RunRecord 中所有候选都有最终状态。

## 进度
⬜ 未开始
