"""LangGraph graph assembly: main graph + per-candidate subgraph."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, TypedDict

from loguru import logger
from langgraph.graph import END, StateGraph
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer  # noqa: F401 (保留类型提示用)
from langgraph.types import Send

from .config import AppConfig
from .llm import LLMClient
from .models import CandidateRecord
from .nodes.backtest import backtest_node
from .nodes.code_exec import code_exec_node
from .nodes.code_fix import code_fix_node
from .nodes.coarse_judge import coarse_judge_node
from .nodes.extract_candidates import extract_candidates_node
from .nodes.fine_filter import fine_filter_node
from .nodes.generate_factor import generate_factor_node
from .nodes.ingest import ingest_node
from .nodes.iterate import iterate_node
from .nodes.relevance_check import relevance_check_node
from .persistence import RunRecorder
from .state import MinerState
from .tools.business_rule import BusinessRules
from .tools.data_schema import DataSchema
from .tools.factor_library import FactorLibrary
from .tools.serde_numpy import NumpySafeSerializer


# ---------- Subgraph state ----------
class PerCandidateState(TypedDict, total=False):
    candidate: dict   # CandidateRecord.model_dump()


def build_graph(cfg: AppConfig, llm: LLMClient):
    holder: dict[str, Any] = {"recorder": None, "tools": None}

    # ---------- Build tools (loaded once) ----------
    factor_library = FactorLibrary(cfg.fine_filter.data_availability.data_schema_path.parent / "factor_library_index.yaml")
    data_schema = DataSchema(cfg.fine_filter.data_availability.data_schema_path)
    business_rules = BusinessRules(cfg.fine_filter.business_rules.rules_path)
    holder["tools"] = (factor_library, data_schema, business_rules)
    logger.info(
        f"Loaded {len(factor_library)} library factors, "
        f"{len(data_schema.fields)} data fields, "
        f"{len(business_rules.rules)} business rules"
    )

    # ================================================================
    # Per-candidate subgraph (M2 + M3)
    # ================================================================
    def _fine_filter(state: dict) -> dict:
        fl, ds, br = holder["tools"]
        return fine_filter_node(state, cfg=cfg, llm=llm,
                                factor_library=fl, data_schema=ds, business_rules=br)

    def _iterate(state: dict) -> dict:
        _, ds, br = holder["tools"]
        return iterate_node(state, cfg=cfg, llm=llm,
                            data_schema=ds, business_rules=br)

    def _generate_factor(state: dict) -> dict:
        _, ds, _ = holder["tools"]
        return generate_factor_node(state, cfg=cfg, llm=llm, data_schema=ds)

    def _code_exec(state: dict) -> dict:
        recorder = holder.get("recorder")
        if recorder is None:
            # Resume: reconstruct run_dir from candidate_id
            cid = state["candidate"]["candidate_id"]
            run_id = cid.rsplit("_c", 1)[0]
            run_dir = Path(cfg.persistence.run_root) / run_id
        else:
            run_dir = recorder.run_dir
        return code_exec_node(state, cfg=cfg, run_dir=run_dir)

    def _code_fix(state: dict) -> dict:
        _, ds, _ = holder["tools"]
        return code_fix_node(state, cfg=cfg, llm=llm, data_schema=ds)

    def _relevance_check(state: dict) -> dict:
        return relevance_check_node(state, cfg=cfg)

    def _backtest(state: dict) -> dict:
        recorder = holder.get("recorder")
        if recorder is None:
            cid = state["candidate"]["candidate_id"]
            run_id = cid.rsplit("_c", 1)[0]
            run_dir = Path(cfg.persistence.run_root) / run_id
        else:
            run_dir = recorder.run_dir
        return backtest_node(state, cfg=cfg, run_dir=run_dir)

    def _save(state: dict) -> dict:
        c = CandidateRecord(**state["candidate"])
        recorder: RunRecorder = holder["recorder"]
        recorder.flush_candidate(c)
        logger.info(f"Subgraph done: {c.candidate_id} status={c.status}")
        return {}

    def _route_after_fine(state: dict) -> str:
        c = CandidateRecord(**state["candidate"])
        if c.fine_passed:
            return "generate_factor"
        if c.status == "fine_iter_failed":
            return "save"
        if c.fine_iteration >= cfg.fine_filter.max_iterations:
            return "save"
        return "iterate"

    def _route_after_code_exec(state: dict) -> str:
        c = CandidateRecord(**state["candidate"])
        if c.code_runnable:
            return "relevance_check"
        if c.code_fix_rounds >= cfg.code_generation.max_fix_rounds:
            return "save"
        return "code_fix"

    def _route_after_relevance(state: dict) -> str:
        c = CandidateRecord(**state["candidate"])
        if c.corr_passed:
            return "backtest"
        return "save"

    subgraph = StateGraph(PerCandidateState)
    subgraph.add_node("fine_filter", _fine_filter)
    subgraph.add_node("iterate", _iterate)
    subgraph.add_node("generate_factor", _generate_factor)
    subgraph.add_node("code_exec", _code_exec)
    subgraph.add_node("code_fix", _code_fix)
    subgraph.add_node("relevance_check", _relevance_check)
    subgraph.add_node("backtest", _backtest)
    subgraph.add_node("save", _save)

    subgraph.set_entry_point("fine_filter")
    subgraph.add_conditional_edges("fine_filter", _route_after_fine, {
        "generate_factor": "generate_factor",
        "iterate": "iterate",
        "save": "save",
    })
    subgraph.add_edge("iterate", "fine_filter")
    subgraph.add_edge("generate_factor", "code_exec")
    subgraph.add_conditional_edges("code_exec", _route_after_code_exec, {
        "code_fix": "code_fix",
        "relevance_check": "relevance_check",
        "save": "save",
    })
    subgraph.add_edge("code_fix", "code_exec")
    subgraph.add_conditional_edges("relevance_check", _route_after_relevance, {
        "backtest": "backtest",
        "save": "save",
    })
    subgraph.add_edge("backtest", "save")
    subgraph.add_edge("save", END)
    compiled_subgraph = subgraph.compile()

    # ================================================================
    # Main graph
    # ================================================================
    g = StateGraph(MinerState)

    def _ingest(state: MinerState) -> dict:
        out = ingest_node(state)
        holder["recorder"] = RunRecorder(
            run_id=out["material"].run_id, cfg=cfg, material=out["material"]
        )
        logger.info(f"Run dir: {holder['recorder'].run_dir}")
        return out

    def _extract(state: MinerState) -> dict:
        out = extract_candidates_node(state, cfg=cfg, llm=llm)
        for c in out.get("candidates", []):
            holder["recorder"].flush_candidate(c)
        return out

    def _coarse(state: MinerState) -> dict:
        out = coarse_judge_node(state, cfg=cfg, llm=llm)
        holder["recorder"].flush_all(out.get("candidates", state.get("candidates", [])))
        return out

    g.add_node("ingest", _ingest)
    g.add_node("extract", _extract)
    g.add_node("coarse", _coarse)
    g.add_node("per_candidate_subgraph", compiled_subgraph)

    g.set_entry_point("ingest")
    g.add_edge("ingest", "extract")
    g.add_edge("extract", "coarse")

    def _route_after_coarse(state: MinerState) -> list[Send]:
        passed = [c for c in state.get("candidates", []) if c.coarse_passed]
        if not passed:
            logger.info("All candidates rejected by coarse judge.")
            return []
        logger.info(f"Dispatching {len(passed)} candidates to subgraph ...")
        return [
            Send("per_candidate_subgraph", {
                "candidate": c.model_dump(),
            })
            for c in passed
        ]

    g.add_conditional_edges("coarse", _route_after_coarse, ["per_candidate_subgraph"])
    g.add_edge("per_candidate_subgraph", END)

    # Checkpointer for resume
    ckpt_path = Path(cfg.persistence.run_root).parent / "checkpoints.sqlite"
    ckpt_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(ckpt_path), check_same_thread=False)
    serde = NumpySafeSerializer(
        allowed_msgpack_modules=[("src.models", "MaterialMeta"), ("src.models", "CandidateRecord")]
    )
    checkpointer = SqliteSaver(conn, serde=serde)
    compiled = g.compile(checkpointer=checkpointer)

    return compiled, holder
