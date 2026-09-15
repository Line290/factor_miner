"""Backtest node: local IC/IR calculation."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from loguru import logger

from ..config import AppConfig
from ..models import CandidateRecord


def backtest_node(state: dict, *, cfg: AppConfig, run_dir: Path) -> dict:
    c = CandidateRecord(**state["candidate"])

    if not c.factor_values_path:
        return {"candidate": c.model_dump()}

    mode = cfg.backtest.mode
    if mode == "off":
        c.status = "backtest_skipped"
        return {"candidate": c.model_dump()}
    if mode == "api":
        logger.warning("Backtest API mode not implemented yet, skipping.")
        c.status = "backtest_skipped"
        return {"candidate": c.model_dump()}

    # ---- local mode ----
    factor_df = pd.read_parquet(c.factor_values_path)
    if "factor" not in factor_df.columns:
        val_col = factor_df.columns[0]
        factor_df = factor_df.rename(columns={val_col: "factor"})

    data_dir = Path(cfg.persistence.run_root).parent / "parquet"
    market_path = data_dir / "market.parquet"
    if not market_path.exists():
        logger.warning(f"Market data not found at {market_path}, skipping backtest.")
        c.status = "backtest_skipped"
        return {"candidate": c.model_dump()}

    market = pd.read_parquet(market_path)

    # Compute next-day return from close_adj
    if "close_adj" not in market.columns:
        logger.warning("close_adj not in market data, skipping backtest.")
        c.status = "backtest_skipped"
        return {"candidate": c.model_dump()}

    market["ret_next"] = market.groupby(level="code")["close_adj"].pct_change().shift(-1)

    # Merge factor with next-day return
    merged = factor_df[["factor"]].join(market[["ret_next"]], how="inner")

    # Check if factor has any non-NaN values
    non_nan = merged["factor"].dropna().shape[0]
    if non_nan == 0:
        logger.warning(f"candidate {c.candidate_id}: factor values are all NaN, skipping backtest.")
        c.status = "backtest_failed"
        c.code_last_error = "compute() returned all-NaN series"
        return {"candidate": c.model_dump()}

    merged = merged.dropna()

    # Universe filter: csi800_member=1, not ST, not suspended, list_days>=min_list_days
    min_list_days = cfg.backtest.local.min_list_days
    for col in ["csi800_member", "is_st", "suspend", "list_days"]:
        if col in market.columns:
            merged = merged.join(market[[col]], how="left")
    if "csi800_member" in merged.columns:
        merged = merged[merged["csi800_member"] == 1]
    if "is_st" in merged.columns:
        merged = merged[merged["is_st"] == 0]
    if "suspend" in merged.columns:
        merged = merged[merged["suspend"] == 0]
    if "list_days" in merged.columns:
        merged = merged[merged["list_days"] >= min_list_days]

    # Daily cross-sectional spearman IC
    def _daily_ic(g):
        if len(g) < 5:
            return None
        return g["factor"].corr(g["ret_next"], method="spearman")

    daily_ic = merged.reset_index().groupby("date").apply(_daily_ic).dropna()

    if len(daily_ic) < 10:
        logger.warning(f"Not enough days ({len(daily_ic)}) for IC calculation.")
        c.status = "backtest_failed"
        return {"candidate": c.model_dump()}

    ic_mean = float(daily_ic.mean())
    ic_std = float(daily_ic.std())
    ir = ic_mean / ic_std if ic_std > 0 else 0.0

    c.ic = round(ic_mean, 4)
    c.ir = round(ir, 3)
    c.status = "backtested"

    # Write report JSON
    report = {
        "candidate_id": c.candidate_id,
        "ic_mean": c.ic,
        "ir": c.ir,
        "ic_std": round(ic_std, 4),
        "n_days": len(daily_ic),
        "universe": "csi800",
    }
    report_path = run_dir / "factors" / f"{c.candidate_id}_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    c.backtest_report_path = str(report_path)

    logger.info(f"Backtest {c.candidate_id}: IC={c.ic}, IR={c.ir}, days={len(daily_ic)}")

    # ---- Auto archive to factor library ----
    aa = cfg.backtest.auto_archive
    if aa.enabled and c.ic is not None and c.ir is not None:
        if c.ic >= aa.min_ic and c.ir >= aa.min_ir:
            _archive_factor(c, cfg)
        else:
            logger.info(
                f"{c.candidate_id} IC={c.ic} IR={c.ir} below archive threshold "
                f"(IC>={aa.min_ic}, IR>={aa.min_ir}), not archived"
            )

    return {"candidate": c.model_dump()}


def _archive_factor(c: CandidateRecord, cfg: AppConfig) -> None:
    """Archive a mined factor to the local factor library."""
    import shutil
    import yaml
    from datetime import datetime

    run_root = Path(cfg.persistence.run_root)
    project_root = run_root.parent.parent          # <root>/data/runs → <root>
    library_dir = run_root.parent / "library_factors"
    index_path = project_root / "configs" / "factor_library_index.yaml"
    library_dir.mkdir(parents=True, exist_ok=True)

    # Unique id: mined_<name>_<date>, dedup if exists
    base_id = f"mined_{c.name.lower().replace(' ', '_')}"
    factor_id = base_id
    existing = set()
    if index_path.exists():
        data = yaml.safe_load(index_path.read_text(encoding="utf-8")) or {}
        existing = {f["id"] for f in data.get("factors", [])}
    suffix = 1
    while factor_id in existing:
        suffix += 1
        factor_id = f"{base_id}_{suffix}"

    # Copy factor values
    src_parquet = Path(c.factor_values_path)
    dst_parquet = library_dir / f"{factor_id}.parquet"
    shutil.copy2(src_parquet, dst_parquet)

    # Append to index yaml
    entry = {
        "id": factor_id,
        "name": c.name,
        "category": "mined",
        "logic_desc": c.logic_desc,
        "formula": c.formula_latex or c.formula_draft,
        "pit_note": f"auto-mined, IC={c.ic}, IR={c.ir}",
        "values_path": str(dst_parquet),
        "source_run_dir": str(c.factor_values_path).split("/factors/")[0],
        "source_candidate_id": c.candidate_id,
        "archived_at": datetime.now().isoformat(),
    }
    if index_path.exists():
        data = yaml.safe_load(index_path.read_text(encoding="utf-8")) or {}
    else:
        data = {"factors": []}
    data.setdefault("factors", []).append(entry)
    index_path.write_text(
        yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    logger.info(f"Archived factor: {factor_id} → {dst_parquet}")
