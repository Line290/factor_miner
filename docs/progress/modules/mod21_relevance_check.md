# mod21 RelevanceCheck 节点

## 职责
因子值跑通后，与因子库中已有因子值做截面相关性，判断是否与已有因子重复。

## 输入
- `candidate.factor_values_path`：新因子值 parquet
- 因子库因子值目录：`data/library_factors/*.parquet`

## 输出
- `candidate.corr_to_library: float`：与库中所有因子的最大 |spearman corr|
- `candidate.corr_passed: bool`
- `candidate.status`：失败时 `high_correlation`

## 逻辑
1. 读新因子值 parquet，索引 `(date, code)`，单列 value；
2. 扫描 `data/library_factors/` 下所有 parquet；
3. 对每个库中因子：
   - 按 date 对齐，每日截面算 spearman(新因子, 库因子)；
   - 取全样本平均 |corr|；
4. 最大 |corr| > `relevance.max_corr_to_library`（0.7）→ 不通过。

## 兜底
- 因子库因子值目录为空 → 跳过检查，`corr_passed=True`，记 `corr_to_library=None`；
- 只在代码计算完成后做这层（逻辑新颖性 M2 已做）。

## 与前后模块串联
- 前：CodeExec 成功产出因子值 parquet
- 后：通过 → Backtest；不通过 → Save（status=high_correlation）

## 进度
⬜ 未开始
