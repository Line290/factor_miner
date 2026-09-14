---
name: factor-calc
description: 量化投资因子计算与回测取数的 Point-in-Time（时间点正确性）强制规范。当用户编写选股/择时/因子策略代码、调用行情/财务/宏观数据接口、计算均线/波动率/截面标准化/排名类指标、审查已有回测代码，或提到"回测好但实盘差""是不是有未来函数""数据对不上"时，必须使用本 skill。Bilingual (Chinese/English) skill covering point-in-time correctness for quantitative factor calculation and backtesting. Use whenever the user writes stock-selection/timing/factor strategy code, calls market/financial/macro data APIs, computes moving averages, volatility, cross-sectional standardization or ranking factors, reviews existing backtest code, or mentions look-ahead bias, "backtest looks great but live trading fails," or survivorship bias — in either Chinese or English.
---

# 量化因子取数 Point-in-Time 规范 / Quant Factor Point-in-Time Skill

> 🇨🇳 **一句话原则：策略在 `t` 日只能使用截至 `t` 日真实可得的数据。**
> 🇬🇧 **One-line rule: a strategy may only use data that was genuinely available as of the close/disclosure of day `t`.**

本 skill 为中英双语版本。两种语言内容对等，选择你正在使用的语言阅读即可；调用本 skill 的模型可以只读需要的那一份参考文件，无需两份都读。
This skill is bilingual. The Chinese and English versions contain equivalent content — read whichever language you're working in. You only need to open the reference file for the language you need, not both.

- 详细规则（中文）/ Detailed rules (Chinese): `references/rules-zh.md`
- Detailed rules (English) / 详细规则（英文）: `references/rules-en.md`

---

## 使用时机 / When to trigger

**中文：**
- 编写新的选股 / 择时 / 因子策略，动手写取数代码之前
- 审查或复盘已有的量化代码 / 回测结果
- 调用行情、财务、宏观数据接口，且涉及日期对齐
- 计算任何均值、趋势线、波动率、回归、截面标准化、排名类指标
- 用户提到"回测收益很好但实盘不行""是不是有未来函数""数据对不上"

**English:**
- Before writing data-fetching code for a new stock-selection / timing / factor strategy
- When reviewing or post-mortem-ing existing quant code / backtest results
- When calling market, financial, or macro data APIs that require date alignment
- When computing any mean, trend line, volatility, regression, cross-sectional standardization, or ranking factor
- When the user says "backtest returns look great but live trading doesn't work," "is there a look-ahead bug," or "the data doesn't line up"

---

## 三句自检 / Three self-check questions

无论中英文，写任何取数/信号代码前先问自己：
Regardless of language, before writing any data-fetching or signal code, ask:

1. **这个数据在回测的这一天，真的已经公开了吗？**（公布日/披露日 + T-1 延迟）
   *Was this data actually public on this exact backtest date?* (announce/disclosure date + T-1 lag)
2. **这个统计量有没有偷偷用到了今天之后的样本？**（窗口右边界、截面分母）
   *Did this statistic secretly use samples from after today?* (window's right edge, cross-sectional denominator)
3. **这个股票/成分/行业，在那天真的存在且可交易吗？**（生存偏差、停牌、涨跌停）
   *Did this stock/index membership/industry classification actually exist and trade on that day?* (survivorship bias, suspension, price limits)

任一答"不确定"，就先按最保守（延迟、剔除、标注）处理，并在注释里写清假设。
If the answer to any is "not sure," default to the most conservative treatment (delay it, exclude it, flag it) and document the assumption in code comments.

---

## 六大主题速查 / Six-topic quick index

详见对应参考文件的同名章节 / see the matching section in the reference files for full detail:

| # | 中文主题 | English topic |
|---|---------|----------------|
| 1 | 行情数据：必须使用复权价 | Market data: always use adjusted prices |
| 2 | 财务数据：取「公布日」，不取「报告期日」 | Financial data: align on announce date, not period-end date |
| 3 | 宏观数据：取「公布日」，且用「当时可得版本」 | Macro data: align on release date, use the vintage available at the time |
| 4 | 数据日期：严格使用需在「当前日期 − 1 天」 | Data cutoff: strictly use `today − 1` as the default `end_date` |
| 5 | 均值 / 趋势 / 截面类指标：严禁未来数据 | Rolling / trend / cross-sectional metrics: no future samples allowed |
| 6 | 其他高频陷阱清单 | Other frequent pitfalls (survivorship, delisting, limit-up/down, liquidity, costs, overfitting…) |

---

## 强制自检清单（每次取数 / 写策略前逐条过）/ Mandatory pre-flight checklist

- [ ] 行情是否使用了复权价？复权因子在回测时点是否已可得？
      Are prices adjusted? Was the adjustment factor actually available at the backtest date?
- [ ] 财务数据是否按**披露日**对齐，而非报告期日？是否落在财报真空期误用了未披露数据？
      Is financial data aligned by **disclosure date**, not period-end? Does it avoid the "reporting vacuum" trap?
- [ ] 宏观数据是否按**公布日**对齐，且使用了**当时初值**而非现行修订值？
      Is macro data aligned by **release date**, using the **first-print vintage**, not today's revised value?
- [ ] 数据查询的 `end_date` 是否默认 `today - 1`？当日数据是否被错误地用于当日成交？
      Does the data query default `end_date` to `today - 1`? Is same-day data wrongly used for same-day execution?
- [ ] 所有均值/趋势/波动率窗口的右边界是否 ≤ 当前回测日（无未来样本）？
      Do all rolling window right-edges stay ≤ the current backtest date?
- [ ] 截面标准化分母是否仅用截至当前时点的横截面，不含未来股票、不用全样本统计回填？
      Does the cross-sectional denominator use only the point-in-time universe — no future listings, no full-sample backfill?
- [ ] 因子输入变量是否全部在信号日已可得（无次日收益、无未来财报/成分股）？
      Are all factor inputs available as of the signal date (no next-day return, no future financials/index membership)?
- [ ] 指数成分股 / 行业分类是否使用信号时点的版本？
      Is index membership / industry classification the point-in-time version?
- [ ] 股票池是否含退市股（无生存偏差）？退市/停牌/涨跌停的不可成交性是否建模？
      Does the universe include delisted stocks (no survivorship bias)? Are delisting/suspension/limit-up-down non-tradability modeled?
- [ ] 交易成本（佣金、印花税、滑点、冲击）是否已计入？
      Are trading costs (commission, stamp duty, slippage, market impact) included?
- [ ] 是否做了样本外 / 滚动验证，避免过拟合？
      Was out-of-sample / walk-forward validation done to avoid overfitting?
- [ ] 数据来源、频率、时区、填充方式是否全策略统一并显式标注？
      Are data source, frequency, timezone, and fill method consistent and explicitly documented across the whole strategy?
- [ ] 截面标准化前是否做了缩尾处理（Winsorize）以消除极端值影响？
      Was Winsorization applied before cross-sectional standardization?
- [ ] 滚动窗口中停牌/缺失值的 `min_periods` 策略是否已明确约定？
      Is the `min_periods` policy for suspensions/missing values in rolling windows explicitly defined?
- [ ] 机器学习场景中，训练集/验证集/测试集是否按时间顺序划分（禁止随机 shuffle）？标签生成是否存在前视偏差？
      For ML: are train/val/test splits chronological (no random shuffle)? Is label generation free of look-ahead bias?
- [ ] 涉及随机采样的回测（Bootstrap/蒙特卡洛）是否固定了随机种子？
      Is the random seed fixed for any bootstrap/Monte-Carlo resampling in the backtest?
- [ ] 北向资金/龙虎榜等资金流数据是否使用了公布后可得的版本？
      Is flow data (e.g., Northbound Connect flows, dragon-tiger list) used only in its post-release-available form?

---

## 正确 vs 错误速查示例 / Correct vs. incorrect quick example

```python
# ❌ 错误 / WRONG — look-ahead bias
df = get_financials(end_date="2023-12-31")   # 年报实际 2024-04-20 才披露 / annual report not disclosed until 2024-04-20
signal = df["roe"] > 0.15                     # 在 2023-12-31 就"预知"了未来年报 / "knows" a future report
sig = close > close.rolling(20).mean()
position = sig.shift(0)                       # T 日信号 T 日成交，未留延迟 / same-day signal, same-day fill — no delay

# ✅ 正确 / CORRECT — point-in-time
df = get_financials(as_of="2023-12-31", by="announce_date")   # 只用当时已披露的数据 / only data disclosed by that date
signal = df["roe"] > 0.15
sig = (close > close.rolling(20).mean()).shift(1)              # T 日信号，T+1 成交 / T-day signal, T+1 fill
cpi = get_macro("CPI", as_of="2024-05-15", vintage="first")    # 取当时初值版本 / use the first-print vintage available then
```

---

如需完整的规则说明、公布延迟参考表、字段口径区分等，请阅读对应语言的参考文件。
For the full rule explanations, disclosure-lag reference tables, and field-definition distinctions, read the reference file for your language.
