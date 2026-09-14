"""CoarseJudge node: score candidates on novelty / feasibility / logic_clarity."""
from __future__ import annotations

import json
from typing import Any

from loguru import logger

from ..config import AppConfig
from ..llm import LLMClient
from ..models import CandidateRecord
from ..prompts import load_prompt
from ..state import MinerState


def _build_system(cfg: AppConfig) -> str:
    dim_lines = "\n".join(
        f"- {d.key}: {d.name} — {d.desc}（1-5 分）" for d in cfg.coarse_judge.dimensions
    )
    return load_prompt("coarse_judge_system", DIMENSIONS=dim_lines)


def _build_user(candidates: list[CandidateRecord]) -> str:
    payload = [
        {
            "candidate_id": c.candidate_id,
            "name": c.name,
            "motivation": c.motivation,
            "logic_desc": c.logic_desc,
            "formula_draft": c.formula_draft,
        }
        for c in candidates
    ]
    return f"候选因子列表：\n{json.dumps(payload, ensure_ascii=False, indent=2)}"


def coarse_judge_node(
    state: MinerState, *, cfg: AppConfig, llm: LLMClient
) -> dict:
    candidates: list[CandidateRecord] = state["candidates"]
    if not candidates:
        return {"coarse_done": True}

    resp = llm.chat_json(
        _build_system(cfg),
        _build_user(candidates),
        node="coarse_judge",
    )

    for c in candidates:
        r: dict[str, Any] = resp.get(c.candidate_id)
        if not r or "scores" not in r:
            logger.warning(f"LLM missing scores for {c.candidate_id}; marking rejected.")
            c.coarse_scores = {}
            c.coarse_avg = 0.0
            c.coarse_passed = False
            c.coarse_judgement = "llm_missing_score"
            c.status = "coarse_rejected"
            continue

        scores = {
            k: max(1.0, min(5.0, float(v))) for k, v in r["scores"].items()
        }
        avg = sum(scores.values()) / max(1, len(scores))
        passed = (
            avg >= cfg.coarse_judge.pass_threshold
            and min(scores.values()) >= cfg.coarse_judge.min_dim_score
        )
        c.coarse_scores = scores
        c.coarse_avg = round(avg, 3)
        c.coarse_passed = passed
        c.coarse_judgement = str(r.get("judgement", ""))
        if not passed:
            c.status = "coarse_rejected"

    n_pass = sum(1 for c in candidates if c.coarse_passed)
    logger.info(f"Coarse judge done: {n_pass}/{len(candidates)} passed.")
    return {"candidates": candidates, "coarse_done": True}
