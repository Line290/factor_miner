"""RelevanceCheck node: correlate new factor with library factors."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from loguru import logger

from ..config import AppConfig
from ..models import CandidateRecord


def relevance_check_node(state: dict, *, cfg: AppConfig) -> dict:
    c = CandidateRecord(**state["candidate"])

    if not c.factor_values_path:
        c.corr_passed = True
        c.corr_to_library = None
        return {"candidate": c.model_dump()}

    library_dir = Path(cfg.persistence.run_root).parent / "library_factors"
    if not library_dir.exists() or not any(library_dir.glob("*.parquet")):
        logger.info(f"No library factors found in {library_dir}, skipping relevance check")
        c.corr_passed = True
        c.corr_to_library = None
        return {"candidate": c.model_dump()}

    # Load new factor
    new_df = pd.read_parquet(c.factor_values_path)
    if "factor" not in new_df.columns:
        # Single-column parquet, assume it's the value
        val_col = new_df.columns[0]
        new_df = new_df.rename(columns={val_col: "factor"})

    max_corr = 0.0
    threshold = cfg.relevance.max_corr_to_library

    for pf in sorted(library_dir.glob("*.parquet")):
        lib_df = pd.read_parquet(pf)
        lib_col = lib_df.columns[0]
        merged = new_df[["factor"]].join(lib_df, how="inner", lsuffix="_new", rsuffix="_lib")
        merged = merged.rename(columns={"factor_new": "factor", f"{lib_col}_lib": "lib_factor"})
        merged = merged.dropna()
        if len(merged) < 30:
            continue
        # Cross-sectional spearman, averaged over dates
        def _daily_corr(g):
            if len(g) < 5:
                return None
            return g["factor"].corr(g["lib_factor"], method="spearman")

        daily = merged.reset_index().groupby("date").apply(_daily_corr).dropna()
        if len(daily) < 10:
            continue
        avg_abs_corr = float(daily.abs().mean())
        if avg_abs_corr > max_corr:
            max_corr = avg_abs_corr

    c.corr_to_library = round(max_corr, 4)
    c.corr_passed = max_corr <= threshold
    if not c.corr_passed:
        c.status = "high_correlation"
        logger.warning(
            f"Relevance check failed: {c.candidate_id} "
            f"max |corr|={max_corr:.3f} > {threshold}"
        )
    else:
        logger.info(f"Relevance check passed: {c.candidate_id} max |corr|={max_corr:.3f}")

    return {"candidate": c.model_dump()}
