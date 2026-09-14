# mod20 · 子图路由改造

## 目标
把子图从"fine_filter → save"改成完整的 M3 流水线：
fine_filter → generate_factor → code_exec → (code_fix ↔ code_exec 循环) → relevance_check(M4) → save

## 产出
- `src/graph.py`（改造子图部分）

## 与前后模块串联
- 上游：M2 已有的 fine_filter / iterate
- 下游：M4 relevance_check（M3 先打占位）

## 子图节点拓扑

```
fine_filter → route:
  ├─ passed → generate_factor → code_exec → route:
  │            ├─ runnable → relevance_check (M4占位) → save
  │            └─ failed & <10轮 → code_fix → code_exec
  │            └─ failed & ≥10轮 → save (code_fix_failed)
  ├─ failed & iter<3 → iterate → fine_filter
  └─ failed & iter≥3 → save (fine_iter_failed)
```

## 实现要点
- M3 阶段 relevance_check 节点先打占位（直接 pass），M4 再接真逻辑；
- code_exec 和 code_fix 之间的回边最多 10 轮；
- 所有节点结束后统一走 save 写 RunRecord。

## 验收标准
1. 通过细筛的候选能走到 generate_factor；
2. 代码能跑通 → 因子值 parquet 落盘；
3. 代码报错 → 自动修复直到跑通或达 10 轮；
4. 最终状态正确。

## 进度
⬜ 未开始
