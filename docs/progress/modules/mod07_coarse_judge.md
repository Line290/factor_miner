# mod07 · CoarseJudge 节点

## 目标
对每个候选按 3 个维度打分，决定是否进入子图（M1 阶段先决定"是否记录为通过/淘汰"）。

## 产出
- `src/nodes/coarse_judge.py`
- `src/prompts/coarse_judge.j2`

## 与前后模块串联
- 上游：mod06（candidates）
- 下游：mod08（根据 `coarse_passed` 路由）；M2 阶段的子图（消费通过粗筛的候选）

## 接口

```python
# src/nodes/coarse_judge.py
def coarse_judge_node(state: MinerState, *,
                      cfg: AppConfig,
                      llm: LLMClient) -> dict:
    """对所有候选批量打分 → 原地写 coarse_* 字段 → 返回 {candidates, coarse_done: True}"""
```

## 实现要点

### Prompt（system）
```
你是因子评审委员会。对候选因子按维度打分（1-5）：
{维度列表，从 cfg.coarse_judge.dimensions 渲染}
对每个候选给出 1-2 句 judgement。
不要评判"业务价值"——那由后续环节判断。
输出 JSON：{"<candidate_id>": {"scores": {"novelty":4,...}, "judgement":"..."}}
```

### 用户消息
把所有候选的 `candidate_id / name / motivation / logic_desc / formula_draft` 列成一个 JSON 数组。

### 通过规则
```python
pass_ = (
    avg >= cfg.coarse_judge.pass_threshold
    and min(scores.values()) >= cfg.coarse_judge.min_dim_score
)
if not pass_:
    c.status = "coarse_rejected"
c.coarse_passed = pass_
```

### 容错
- LLM 漏给某个 candidate_id 打分：该候选标记 `coarse_passed=False`，`coarse_judgement="llm_missing_score"`，继续跑不中断；
- 分数不在 1-5：clamp。

## 验收标准
1. 给 3 个 mock 候选，LLM 返回 3 个分数；
2. avg < pass_threshold 的候选被标记 `coarse_rejected`；
3. LLM 漏打分时不抛异常；
4. 节点返回后，所有候选的 `coarse_avg / coarse_passed / coarse_judgement` 都非空。

## 进度
⬜ 未开始
