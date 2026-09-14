# mod18 · CodeExec 节点

## 目标
调 CodeSandbox 跑因子代码，成功则保存因子值 parquet，失败则记录报错。

## 产出
- `src/nodes/code_exec.py`

## 与前后模块串联
- 上游：GenerateFactor / CodeFix
- 下游：成功 → RelevanceCheck（M4）；失败 → CodeFix（如果 <10 轮）

## 接口

```python
def code_exec_node(state: dict, *, cfg: AppConfig,
                    recorder: RunRecorder) -> dict:
    """调 sandbox 跑代码 → 更新 candidate.code_runnable / factor_values_path / code_last_error"""
```

## 实现要点
- 因子值输出到 `data/runs/{run_id}/factors/{candidate_id}_values.parquet`
- 成功后 `c.code_runnable = True`，`c.factor_values_path = str(...)`
- 失败后 `c.code_runnable = False`，`c.code_last_error = stderr 截断`
- `c.code_fix_rounds += 1`（从 CodeFix 回来时计数）

## 路由
```python
def route_after_code_exec(state):
    c = state["candidate"]
    if c["code_runnable"]:
        return "relevance_check"   # M4
    if c["code_fix_rounds"] >= cfg.code_generation.max_fix_rounds:
        c["status"] = "code_fix_failed"
        return "save"
    return "code_fix"
```

## 验收标准
1. 代码能跑通 → 因子值 parquet 存在；
2. 代码报错 → code_last_error 有内容；
3. 超过 10 轮 → status=code_fix_failed。

## 进度
⬜ 未开始
