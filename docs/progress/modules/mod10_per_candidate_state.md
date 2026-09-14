# mod10 · Per-Candidate 子图 State

## 目标
定义单个候选因子在子图中流转的 State。子图与主图通过 Send 通信，主图把 `CandidateRecord` 作为子图输入。

## 产出
- `src/state.py`（追加 PerCandidateState）

## 与前后模块串联
- 上游：主图 CoarseJudge 节点，通过 `Send("per_candidate_subgraph", payload)` 传入
- 下游：FineFilter / Iterate /（M3 的 GenerateFactor 等）

## 接口

```python
class PerCandidateState(TypedDict, total=False):
    candidate: CandidateRecord
    # 共享上下文（通过 Send payload 传入）
    run_id: str
    cfg: AppConfig          # 注意：pydantic 对象，checkpointer 序列化时要注意
    llm: LLMClient          # 同上，不序列化，运行时注入
    recorder: RunRecorder    # 同上
```

## 实现要点
- `cfg / llm / recorder` 不进 checkpoint（它们是运行时对象）。LangGraph 支持在节点闭包里注入，State 里只放可序列化数据。
- 实际做法：子图节点函数从闭包拿 cfg/llm/recorder，State 里只放 `candidate` 和 `run_id`。
- 这样 checkpoint 只序列化 candidate，重启后重新注入 cfg/llm/recorder。

## 验收标准
1. 子图能从主图收到 CandidateRecord；
2. 子图结束后，最终的 CandidateRecord 写回 RunRecord。

## 进度
⬜ 未开始
