"""CodeExec node: run factor code in sandbox."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from loguru import logger

from ..config import AppConfig
from ..models import CandidateRecord, CodeFixStep
from ..tools.code_sandbox import run_factor_code


def code_exec_node(state: dict, *, cfg: AppConfig, run_dir: Path) -> dict:
    c = CandidateRecord(**state["candidate"])

    if not c.python_code:
        c.code_runnable = False
        c.code_last_error = "No python_code generated"
        return {"candidate": c.model_dump()}

    output_path = run_dir / "factors" / f"{c.candidate_id}_values.parquet"
    data_dir = Path(cfg.persistence.run_root).parent / "parquet"

    result = run_factor_code(
        code=c.python_code,
        required_fields=c.required_fields,
        data_dir=data_dir,
        output_path=output_path,
        python_bin=cfg.code_generation.python_bin,
        timeout_sec=cfg.code_generation.sandbox_timeout_sec,
    )

    if result.success:
        c.code_runnable = True
        c.factor_values_path = result.values_path
        c.code_last_error = None
        c.status = "code_runnable"
        logger.info(f"CodeExec OK: {c.candidate_id} → {result.values_path}")
    else:
        c.code_runnable = False
        c.code_last_error = result.error
        c.code_fix_rounds += 1
        if c.code_fix_rounds >= cfg.code_generation.max_fix_rounds:
            c.status = "code_fix_failed"
        # traceback 的异常类型在末尾，取尾部避免把关键信息截掉
        logger.warning(f"CodeExec failed: {c.candidate_id} "
                        f"(round {c.code_fix_rounds}), error: ...{result.error[-500:]}")

    # Record this round
    c.code_fix_history.append(CodeFixStep(
        round=c.code_fix_rounds,
        python_code=c.python_code,
        success=c.code_runnable,
        error=c.code_last_error,
        timestamp=datetime.now(),
    ))

    return {"candidate": c.model_dump()}
