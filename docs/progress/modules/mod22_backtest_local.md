# mod22 Backtest Local 节点

## 职责
本地因子分析：算 IC / IR / 分层收益，不依赖 alphalens（避免装包）。

## 输入
- `candidate.factor_values_path`：因子值 parquet
- `data/parquet/market.parquet`：行情数据（取 close_adj 算次日收益）
- 配置：`backtest.local.universe`（股票池）、`start_date`

## 输出
- `candidate.ic: float`：全样本 IC 均值
- `candidate.ir: float`：IC 均值 / IC 标准差
- `candidate.backtest_report_path`：JSON 摘要路径
- `candidate.status`：`backtested`

## 指标定义
- **IC**：每日截面 spearman(因子值, 次日收益率)，取全样本均值；
- **IR**：mean(IC) / std(IC)；
- 不做复杂分层回测（alpha-lens 后续接入），先给核心 IC/IR。

## 股票池过滤
- 按 `csi800_member` 过滤（默认 csi800）；
- 剔除 is_st=1、suspend=1；
- 上市不满 252 天剔除。

## 输出 JSON
```json
{
  "ic_mean": 0.045,
  "ir": 1.2,
  "ic_std": 0.038,
  "n_days": 244,
  "universe": "csi800"
}
```

## 与前后模块串联
- 前：RelevanceCheck 通过
- 后：Save（status=backtested）

## 进度
⬜ 未开始
