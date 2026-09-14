# mod08 · 主图组装

## 目标
把 mod05/06/07 三个节点挂到 LangGraph StateGraph 上，跑通"输入材料 → 候选 → 粗筛 → 结束"的主流程。

## 产出
- `src/graph.py`

## 与前后模块串联
- 上游：mod03（State）、mod05-07（节点）
- 下游：mod09（图结束时写 RunRecord）；M2 在主图上加子图扇出

## 接口

```python
# src/graph.py
from langgraph.graph import StateGraph, END

def build_graph(cfg: AppConfig, llm: LLMClient) -> StateGraph:
    g = StateGraph(MinerState)
    g.add_node("ingest", lambda s: ingest_node(s))
    g.add_node("extract", lambda s: extract_candidates_node(s, cfg=cfg, llm=llm))
    g.add_node("coarse", lambda s: coarse_judge_node(s, cfg=cfg, llm=llm))

    g.set_entry_point("ingest")
    g.add_edge("ingest", "extract")
    g.add_edge("extract", "coarse")

    def route_after_coarse(state):
        passed = [c for c in state["candidates"] if c.coarse_passed]
        if passed:
            return "end_with_factors"   # M2 这里换成 Send 扇出
        return "end_all_rejected"

    g.add_conditional_edges("coarse", route_after_coarse, {
        "end_with_factors": END,
        "end_all_rejected": END,
    })
    return g.compile()
```

## 实现要点
- 节点函数用 lambda 闭包注入 `cfg` 和 `llm`（LangGraph 节点签名是 `state -> dict`）；
- M1 阶段主图终点是 END，不扇子图；
- 图编译后暴露给 `main.py` 调用 `graph.invoke(initial_state, config={"configurable": {"thread_id": run_id}})`；
- M2 改造点预留：`route_after_coarse` 改成返回 `Send("per_candidate_subgraph", {...})`，不改其他节点。

## 验收标准
1. 给一篇 PDF，能从 ingest 跑到 coarse，无报错；
2. State 里最终有完整的 `candidates` 列表（含粗筛结果）；
3. 全部淘汰时也能正常结束；
4. 打印图结构 `graph.get_graph().draw_mermaid()` 能看到 3 个节点。

## 进度
⬜ 未开始
