"""Generate a mock market.parquet for M3 testing.
Replace this with real data when available.
"""
import numpy as np
import pandas as pd
from pathlib import Path

np.random.seed(42)

dates = pd.bdate_range("2023-01-01", "2024-01-01")
codes = [f"{i:06d}.SH" for i in range(1, 81)]  # 80 stocks ~ csi800 mock

index = pd.MultiIndex.from_product([dates, codes], names=["date", "code"])
n = len(index)

df = pd.DataFrame({
    "close_adj": np.cumprod(1 + np.random.randn(n) * 0.02) + 50,
    "open_adj": np.cumprod(1 + np.random.randn(n) * 0.02) + 49,
    "adjust_factor": 1.0,
    "volume": np.random.randint(1e6, 1e8, n).astype(float),
    "amount": np.random.uniform(1e7, 1e9, n),
    "close": np.random.uniform(10, 100, n),
    "open": np.random.uniform(10, 100, n),
    "high": np.random.uniform(10, 100, n),
    "low": np.random.uniform(10, 100, n),
    "vwap": np.random.uniform(10, 100, n),
    "pe_ttm": np.random.uniform(5, 80, n),
    "pb": np.random.uniform(0.5, 10, n),
    "ps_ttm": np.random.uniform(0.5, 20, n),
    "dv_ttm": np.random.uniform(0, 0.08, n),
    "total_mv": np.random.uniform(1e9, 1e12, n),
    "circ_mv": np.random.uniform(5e8, 5e11, n),
    "float_shares": np.random.uniform(1e7, 1e10, n),
    "is_st": np.random.choice([0, 0, 0, 0, 1], n),
    "list_days": np.random.randint(10, 3000, n),
    "suspend": 0,
    "limit_status": 0,
    "csi800_member": 1,
    "csi1000_member": 0,
    "north_bound_holding": np.random.uniform(0, 1e6, n),
    "north_bound_holding_ratio": np.random.uniform(0, 0.05, n),
}, index=index)

out = Path("data/parquet/market.parquet")
out.parent.mkdir(parents=True, exist_ok=True)
df.to_parquet(out)
print(f"Generated mock data: {out} shape={df.shape}")
print(f"Columns: {list(df.columns)}")
