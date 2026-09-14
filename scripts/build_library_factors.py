"""Build library factor values from market.parquet.
Only factors computable from available fields are generated.
Output: data/library_factors/{factor_id}.parquet
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "parquet" / "market.parquet"
OUT = ROOT / "data" / "library_factors"
OUT.mkdir(parents=True, exist_ok=True)


def compute_factors(df: pd.DataFrame) -> dict[str, pd.Series]:
    close = df["close_adj"]
    ret_1d = close.groupby(level="code").pct_change()
    turnover = df["volume"] / df["float_shares"]

    factors = {
        # momentum
        "mom_20": close.groupby(level="code").pct_change(20),
        "mom_60": close.groupby(level="code").pct_change(60),
        "mom_12_1": close.groupby(level="code").shift(21) / close.groupby(level="code").shift(252) - 1,

        # volatility
        "vol_20": ret_1d.groupby(level="code").rolling(20).std().reset_index(level=0, drop=True),
        "vol_60": ret_1d.groupby(level="code").rolling(60).std().reset_index(level=0, drop=True),
        "downside_vol": ret_1d.where(ret_1d < 0).groupby(level="code").rolling(60).std().reset_index(level=0, drop=True),

        # liquidity
        "liq_turnover_20": turnover.groupby(level="code").rolling(20).mean().reset_index(level=0, drop=True),
        "liq_amihud": (ret_1d.abs() / df["amount"]).groupby(level="code").rolling(20).mean().reset_index(level=0, drop=True),

        # size
        "size_log_mv": np.log(df["total_mv"]),
        "size_circ_mv": df["circ_mv"],

        # technical
        "tech_reversal_5": -close.groupby(level="code").pct_change(5),
        "tech_ma_bias": close / close.groupby(level="code").rolling(20).mean().reset_index(level=0, drop=True) - 1,

        # value
        "val_bp": 1.0 / df["pb"],
        "val_ep": 1.0 / df["pe_ttm"],
    }
    return factors


def main():
    if not DATA.exists():
        print(f"Market data not found: {DATA}")
        sys.exit(1)

    df = pd.read_parquet(DATA)
    print(f"Loaded market data: {df.shape}, columns: {list(df.columns)}")

    factors = compute_factors(df)
    for fid, series in factors.items():
        out_path = OUT / f"{fid}.parquet"
        series.name = "factor"
        series.to_frame().to_parquet(out_path)
        print(f"  {fid}: {series.dropna().shape[0]} non-NaN → {out_path.name}")

    print(f"\nDone. {len(factors)} library factors written to {OUT}")


if __name__ == "__main__":
    main()
