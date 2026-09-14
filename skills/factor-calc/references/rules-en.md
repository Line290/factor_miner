# Quant Strategy Data-Sourcing Pitfalls (English Detailed Version)

> **One-line principle: Point-in-Time correctness.**
> Data a strategy can "see" on day `t` must be data that was genuinely available by the close of trading / by disclosure on day `t`.
> Using any information that only existed after day `t` (prices, financial reports, macro data, index membership, revised values...) is look-ahead bias.
> It turns a backtest into "predicting the past with the future," and it will inevitably fail in live trading.

## 1. Market Data: Always Use Adjusted Prices

**Default rule: technical signals and returns should always use adjusted prices, never raw (unadjusted) prices.**

| Adjustment method | Meaning | Best for | Caveat |
|---|---|---|---|
| Forward (backward-looking) adjustment | Historical prices are scaled using adjustment factors anchored to the **most recent trading day**, so the latest price equals the real market price | Charting, technical patterns, indicator continuity | Historical prices are not the real transacted prices |
| Backward (forward-looking) adjustment | Anchored to a **fixed historical date**, adjustments accumulate forward from there | Long-horizon true returns, dividend-reinvested NAV comparisons | Current price ≠ real market price |
| No adjustment | Real transacted prices, but has ex-dividend/ex-rights gaps | Cases that need the real transacted price/volume | Gaps distort returns and indicators |

Pitfalls:

1. Unadjusted prices have gaps at ex-dividend/ex-rights dates, producing fake return spikes/crashes on those days and distorting MA, MACD, Bollinger Bands, RSI, etc.
2. **Don't mix conventions in one backtest**: use adjusted prices for signals and returns; if you need real transacted price/volume, pull the unadjusted field separately and label it explicitly — never subtract or concatenate the two directly.
3. **Adjustment factors themselves lag**: the ex-dividend announcement date is not the same as the execution date. Confirm the adjustment factor used was actually available at the backtest timestamp — don't "know" a new factor before the ex-dividend event happens.
4. Futures / convertible bonds: rolling the front-month contract creates jumps; use an adjusted continuous contract or handle the roll explicitly, or you'll get a fake price gap.
5. If the strategy relies on dividend reinvestment, explicitly decide (and keep consistent) whether the backtest assumes reinvestment on the ex-dividend day itself.
6. Under forward adjustment, **historical prices before the ex-dividend date are pushed down** (in dividend scenarios), which can severely distort absolute-price-level strategies (e.g., "buy stocks priced under ¥20").

## 2. Financial Data: Align on "Announcement Date," Not "Reporting Period Date"

Key distinction:

- **Reporting period date** (e.g., 2023-12-31): the end of the accounting period the data covers.
- **Announcement / disclosure date** (e.g., 2024-04-20): the date the report was actually released to the public.

**Using data at the reporting-period date = "knowing" a report before it was published = severe look-ahead bias.**

Pitfalls:

1. Financial data must be aligned to the backtest timeline by **disclosure date**, not reporting period. On day `t`, the strategy may only use financial data disclosed by day `t`.
2. Watch for the "reporting vacuum" created by statutory disclosure deadlines:
   - Q1 report: due by Apr 30 of the same year
   - Interim (H1) report: due by Aug 31
   - Q3 report: due by Oct 31
   - Annual report: due by Apr 30 of the following year (some extend to June)
   During the vacuum period, use the **most recently disclosed** report (e.g., in August, use the Q1 report — not the not-yet-disclosed interim report).
3. **Earnings previews / flash reports / formal reports** are different information tiers: a flash report precedes the formal report and can be used as an early signal, but must be tagged by tier — don't align the formal report's final figure to the flash report's timestamp.
4. Watch for **restatements and retroactive corrections**: the backtest should use the version originally disclosed at the time, not a later "cleaned up" corrected version.
5. TTM / rolling metrics must be computed from the **latest disclosed reporting period**, and must not roll into a quarter that hasn't been disclosed yet.
6. Be careful with field definitions: net profit attributable to parent vs. non-recurring-adjusted net profit, weighted vs. diluted ROE, whether revenue includes retroactive restatement, etc.
7. Precise dividend-related dates: the record date, the ex-dividend date, and the payment date are three different dates. Dividend reinvestment should occur on the ex-dividend date, using the post-ex-dividend price — not the payment date.

## 3. Macro Data: Align on "Release Date," Using the "Vintage Available at the Time"

Key distinction: the period a metric covers (e.g., CPI for March 2023) ≠ its release date (typically the 9th–15th of the following month).

Typical release lags for common China macro indicators (for reference only — verify against the official source):

| Indicator | Approximate release timing | Notes |
|---|---|---|
| PMI | Around the 1st of the following month | Released early in the month |
| CPI / PPI | 9th–15th of the following month | Base-period adjustments are common |
| Total Social Financing / Credit | 10th–15th of the following month | PBoC convention |
| M1 / M2 | 10th–15th of the following month | PBoC convention |
| Industrial Value-Added | Around the 15th of the following month | — |
| GDP | ~15–20 days after quarter-end (preliminary), revised multiple times after | Major annual revisions occur |

Pitfalls:

1. Macro indicators typically lag 1–2 months; you **must align by release date** — don't pull data into the backtest "early" using the period date.
2. Macro data generally goes through **preliminary → final → revised** stages: the backtest must use the **vintage that was available at the time**, never today's revised final value (or it's look-ahead).
3. Different sources report inconsistent conventions (National Bureau of Statistics, PBoC, third-party vendors) — **standardize on one authoritative source across the whole strategy** to avoid mixing conventions across indicators.
4. Watch for revision windows (GDP annual revisions, CPI base-period rebasing) — these revisions rewrite historical values after the fact, breaking point-in-time correctness.

## 4. Data Date Cutoff: Strictly Use "Current Date − 1 Day"

Rule: data released on the current day (T) is, by default, not usable for execution on day T in a strict backtest — it earliest becomes available/tradable on T+1.

Pitfalls:

1. Market data: T-day closing price is only finalized after the T-day close auction; intraday data is a partial snapshot and cannot be treated as a "closing price signal" executed the same day.
2. Financial/news/announcement data: mostly released after market close, so a T-day signal should be set to execute on T+1 (or be modeled as an after-hours decision executed the next trading day).
3. **Signal date = the date the data becomes available; execution date = signal date + minimum lag (usually T+1).** Don't default to "signal generated at T close, executed at T close" unless you have explicitly modeled after-hours decision-making plus next-day execution.
4. Watch special sessions: night sessions, call auctions, after-hours fixed-price trading — their "same day" boundary and signal-availability rules need to be defined separately.
5. Practical tip: default the `end_date` of any data query to `today - 1`; if you truly need same-day data, state that explicitly and accept the constraint that it cannot be used for same-day execution.

## 5. Moving Average / Trend / Cross-Sectional Metrics: No Future Data Allowed

Anything whose "statistical window" or "normalization denominator" includes samples from after the current point in time is a look-ahead function.

Pitfalls:

1. Moving average (MA), exponential smoothing (EWMA), regression trend lines, volatility (rolling std), Bollinger Bands, RSI, ATR, etc.: **the right edge of the window must be ≤ the current backtest date** — never let future N-day data enter the calculation.
2. **Cross-sectional standardization** (z-score, quantile rank, industry-neutralization, market-cap neutralization):
   - The denominator (market-wide mean, std, market cap) must use **the cross-section as of the current point in time**;
   - It must not include stocks that will only be listed/included in the future, and must not backfill using full-sample (including future) statistics.
3. **Every input to a factor value must be available as of the signal date**: a factor that references next-day returns, future financial reports, or future index membership is invalid.
4. **Index membership / industry classification must use the point-in-time version**: periodic membership rebalancing and industry re-classification are future events — backtesting the past with "today's membership" produces both look-ahead and survivorship bias.
5. Cross-sectional stock selection (e.g., "top 10% market-wide by rank"): the ranking universe must be all stocks tradable at that time (including ones that later delisted) — it must not implicitly filter using future survival status.

## 6. Other Frequent Pitfalls (check every item before backtesting)

- **Survivorship bias**: if the backtest universe only includes currently-listed stocks and omits stocks that were later flagged ST or delisted, returns will be systematically overstated. The universe must include all historically listed instruments and their delisting/removal status.
- **Delisting handling**: a delisted stock has no price after its last trading day — you need an explicit rule (use the delisting price, mark to zero, or exclude and compute a disposal return); silently dropping it inflates returns.
- **Non-tradability at price limits**: you can't buy at a limit-up or sell at a limit-down. Filling unconditionally at the closing price is unrealistic — add a constraint checking whether the day hit its limit and whether the order could actually fill.
- **Changing ST price-limit bands**: ST-designated stocks' daily price-limit band changed from 10% to 5% — the backtest needs to determine the applicable threshold dynamically, not hardcode 10% or 5%.
- **Trading halts**: positions can't be rebalanced during a suspension — the backtest must freeze the position and defer the trade instruction, not assume it's tradable at will.
- **Liquidity / market impact**: low-liquidity, small-cap strategies face large market impact; you need volume constraints (e.g., cap fills at some fraction of the day's traded volume) and a slippage model — don't assume unlimited capacity.
- **Underestimated or omitted trading costs**: commission, stamp duty, transfer fees, slippage, market impact. Backtest returns that omit costs are not credible.
- **Overfitting / data snooping**: over-optimizing in-sample, grid-searching parameters, multiple testing. Use out-of-sample, rolling-window, and walk-forward validation; penalize complexity and control the number of nominal tests run.
- **Frequency mismatch**: using a daily-frequency factor for minute-level decisions, or misaligning data joined across different frequencies — define alignment and backfill rules explicitly.
- **Outlier / missing-value handling**: zeros/NaNs from suspensions, and extreme values, need careful, documented fill methods: forward-fill (ffill) doesn't introduce future information but may mask a suspension signal; backward-fill (bfill) introduces future information and must never be used.
- **Financial-report seasonality**: YoY/QoQ base-period differences vary by industry and reporting period — keep conventions consistent and seasonally adjust when comparing across periods.
- **Benchmark choice**: use the correct market benchmark (CSI 300 / CSI 500 / CSI All-Share, etc.) and avoid survivorship-biased benchmarks.
- **Timestamps and time zones**: cross-market data, night sessions, and data-landing delays require a unified timezone and "trading day" definition.
- **Backfill trap**: historical data returned by third-party APIs often already contains later revisions, which breaks point-in-time correctness — confirm whether the API provides true historical point-in-time snapshots before backtesting.
- **New/recently-listed stocks' first-day data**: newly listed stocks have no historical adjusted-price data on their first day, and price-limit rules differ (no price limit for the first 5 trading days) — this needs special handling or it produces spurious signals.
- **Machine learning scenarios**: train/validation/test splits must not be randomly shuffled — split chronologically (e.g., `TimeSeriesSplit`). Label generation must also avoid look-ahead bias (e.g., if using a future return as a label, confirm whether that return was actually knowable at feature-generation time).
- **Data-source consistency**: different data vendors (Wind, TongHuaShun iFinD, Eastmoney, TDX, JoinQuant, Tushare) may compute the same metric differently (e.g., market cap based on total shares vs. free-float shares, differing industry-classification standards) — standardize on one data source across the whole strategy.
- **Hidden forms of look-ahead bias in backtests**: using full-sample optimal parameters; determining industry-neutralization groupings using a future state (e.g., neutralizing historical data using today's industry classification); using suspension/limit-up-down status that was only knowable in the future as a feature.
- **Log returns vs. simple returns**: log returns (ln(Pt/Pt-1)) are time-additive (multi-day log return = sum of daily log returns), while simple returns are not additive (they can't be summed directly — they must be compounded via multiplication). Choosing one or the other changes how multi-day cumulative returns are computed, so keep the convention consistent.
- **Correct annualization**: for daily-frequency returns, simple-return annualization = (1 + daily return)^252 − 1, while log-return annualization = daily log return × 252. Mixing the two produces a biased annualized figure.
- **Winsorization before cross-sectional standardization**: factor values typically need winsorizing (e.g., 3-sigma or quantile-based clipping) before cross-sectional standardization, to remove the influence of extreme values on the result.
- **Missing values / suspensions inside rolling windows**: when a stock is suspended (NaN) within a rolling window, `rolling().mean()`'s behavior depends on the `min_periods` parameter. Too small a `min_periods` computes the metric from too little valid data, distorting it; too large a value means the metric stops updating for a long time after a suspension. Define the `min_periods` policy explicitly.
- **Availability of flow data (Northbound Connect, dragon-tiger list, etc.)**: Northbound Connect flows are published by the exchange before 18:00 on the trading day; the dragon-tiger list is published after 16:30. If a strategy uses this data after market close to generate next-day signals, confirm the data was actually available at signal-generation time — some data sources may not update until the following morning.
- **Timing issues in performance evaluation**: the risk-free rate used in a Sharpe ratio must be aligned to the backtest date — don't use today's risk-free rate to retroactively compute a historical Sharpe ratio; maximum drawdown should be computed over the full backtest window, not just in-sample.

## Mandatory Pre-Flight Checklist

See the "Mandatory pre-flight checklist" section in the root `SKILL.md` — content is identical across both languages and is not repeated here.
