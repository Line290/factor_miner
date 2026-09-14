"""FineFilter node: three checks (novelty / data availability / business rules)."""
from __future__ import annotations

import json
from datetime import datetime

from loguru import logger

from ..config import AppConfig
from ..llm import LLMClient
from ..models import CandidateRecord, IterationStep
from ..prompts import load_prompt
from ..tools.business_rule import BusinessRules
from ..tools.data_schema import DataSchema
from ..tools.factor_library import FactorLibrary


def _check_novelty(c: CandidateRecord, lib: FactorLibrary, llm: LLMClient) -> dict:
    prompt = f"""已有因子库：
{lib.describe_for_llm()}

新候选因子：
- name: {c.name}
- logic_desc: {c.logic_desc}
- formula_draft: {c.formula_draft}

判断新候选是否与库中某个因子实质等价。"""
    try:
        resp = llm.chat_json(
            load_prompt("novelty_check_system"), prompt, node="novelty_check"
        )
        equivalent = bool(resp.get("equivalent", False))
        matched = resp.get("matched_id")
        reason = str(resp.get("reason", ""))
        return {
            "passed": not equivalent,
            "matched_id": matched,
            "reason": reason,
        }
    except Exception as e:
        logger.warning(f"Novelty check failed for {c.candidate_id}: {e}")
        return {"passed": True, "matched_id": None, "reason": f"llm_error: {e}"}


def _check_data_availability(
    c: CandidateRecord, schema: DataSchema, llm: LLMClient
) -> dict:
    user_msg = f"""因子描述：
- name: {c.name}
- motivation: {c.motivation}
- logic_desc: {c.logic_desc}
- formula_draft: {c.formula_draft}

可用数据字典：
{schema.summary_for_llm()}"""
    try:
        resp = llm.chat_json(
            load_prompt("data_avail_system"), user_msg, node="data_avail"
        )
        fields_needed = resp.get("fields_needed", [])
        fields_available = resp.get("fields_available", [])
        fields_missing = resp.get("fields_missing", [])
        fatal = bool(resp.get("fatal", False))
        reason = str(resp.get("reason", ""))
    except Exception as e:
        return {
            "passed": False,
            "required_fields": [],
            "missing_fields": [f"llm_judge_failed: {e}"],
            "derivable_fields": [],
            "fatal_missing": [],
            "reason": f"LLM 判断失败: {e}",
        }

    # Fallback validation: schema.check() 兜底，防止 LLM 撒谎说字段有但其实没有
    fallback = schema.check(fields_needed)
    if not fallback.passed and not fatal:
        # LLM 说有但实际缺 → 以代码检查为准
        reason = f"{reason} [兜底校验: {fallback.reason}]"
        fields_missing = fallback.missing_fields

    passed = len(fields_missing) == 0
    return {
        "passed": passed,
        "required_fields": fields_needed,
        "missing_fields": fields_missing,
        "derivable_fields": fallback.derivable_fields,
        "fatal_missing": fields_missing if fatal else [],
        "reason": reason,
    }


def _check_business(
    c: CandidateRecord, rules: BusinessRules, llm: LLMClient
) -> dict:
    result = rules.check_with_llm(c, llm)
    return {
        "passed": result.passed,
        "violated": result.violated,
        "reason": result.reason,
    }


def fine_filter_node(
    state: dict,
    *,
    cfg: AppConfig,
    llm: LLMClient,
    factor_library: FactorLibrary,
    data_schema: DataSchema,
    business_rules: BusinessRules,
) -> dict:
    c: CandidateRecord = CandidateRecord(**state["candidate"]) if isinstance(state["candidate"], dict) else state["candidate"]
    checks: dict = {}

    if cfg.fine_filter.novelty_check.enabled:
        checks["novelty"] = _check_novelty(c, factor_library, llm)

    if cfg.fine_filter.data_availability.enabled:
        checks["data_avail"] = _check_data_availability(c, data_schema, llm)

    if cfg.fine_filter.business_rules.enabled:
        checks["biz"] = _check_business(c, business_rules, llm)

    c.fine_checks = checks
    c.fine_passed = all(v.get("passed", False) for v in checks.values())

    if not c.fine_passed:
        parts = []
        for k, v in checks.items():
            if not v.get("passed", False):
                parts.append(f"[{k}] {v.get('reason', '')}")
        c.fine_feedback = "\n".join(parts)
        c.fine_iteration += 1
        # Fatal: 数据字典明确 unavailable 的字段，迭代也没用
        fatal_fields = checks.get("data_avail", {}).get("fatal_missing", [])
        if fatal_fields or c.fine_iteration >= cfg.fine_filter.max_iterations:
            c.status = "fine_iter_failed"
    else:
        c.fine_feedback = None

    # Record snapshot for this round
    c.iteration_history.append(IterationStep(
        iteration=c.fine_iteration,
        motivation=c.motivation,
        logic_desc=c.logic_desc,
        formula_draft=c.formula_draft,
        fine_checks=checks,
        fine_feedback=c.fine_feedback,
        passed=c.fine_passed,
        timestamp=datetime.now(),
    ))

    logger.info(
        f"Fine filter {c.candidate_id}: passed={c.fine_passed}, "
        f"iter={c.fine_iteration}, feedback={c.fine_feedback or 'n/a'}"
    )
    return {"candidate": c.model_dump()}
