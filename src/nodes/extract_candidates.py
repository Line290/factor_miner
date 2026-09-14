"""ExtractCandidates node: LLM splits material text into N candidate factors."""
from __future__ import annotations

import re
from typing import Any

from loguru import logger

from ..config import AppConfig
from ..llm import LLMClient
from ..models import CandidateRecord
from ..prompts import load_prompt
from ..state import MinerState


def _split_into_chunks(text: str, max_chars: int = 6000) -> list[str]:
    """Split by <<<PAGE n>>> markers; a page longer than max_chars is re-split."""
    pages = re.split(r"(?=<<<PAGE \d+>>>)", text)
    chunks: list[str] = []
    for page in pages:
        if not page.strip():
            continue
        if len(page) <= max_chars:
            chunks.append(page)
        else:
            # Re-split by double newlines
            parts = page.split("\n\n")
            buf = ""
            for part in parts:
                if len(buf) + len(part) > max_chars and buf:
                    chunks.append(buf)
                    buf = part
                else:
                    buf = buf + "\n\n" + part if buf else part
            if buf:
                chunks.append(buf)
    return chunks


def _dedup(cands: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, Any]] = []
    for c in cands:
        key = (str(c.get("name", "")).strip().lower(), str(c.get("logic_desc", ""))[:50])
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def extract_candidates_node(
    state: MinerState, *, cfg: AppConfig, llm: LLMClient
) -> dict:
    text = state["material_text"]
    run_id = state["run_id"]
    chunks = _split_into_chunks(text)
    logger.info(f"Extracting candidates from {len(chunks)} chunks ...")

    raw_candidates: list[dict[str, Any]] = []
    for i, chunk in enumerate(chunks):
        try:
            resp = llm.chat_json(
                load_prompt("extract_candidates_system"),
                f"=== 材料片段 {i+1}/{len(chunks)} ===\n{chunk}",
                node="extract_candidates",
            )
            raw_candidates.extend(resp.get("candidates", []))
        except Exception as e:
            logger.warning(f"Chunk {i+1} failed to extract: {e}; skipping")

    deduped = _dedup(raw_candidates)[: cfg.extraction.max_candidates_per_doc]

    candidates: list[CandidateRecord] = []
    for idx, c in enumerate(deduped, start=1):
        candidates.append(
            CandidateRecord(
                candidate_id=f"{run_id}_c{idx:02d}",
                name=str(c.get("name", f"cand_{idx}")),
                motivation=str(c.get("motivation", "")),
                logic_desc=str(c.get("logic_desc", "")),
                formula_draft=str(c.get("formula_draft", "")),
                source_page=int(c["source_page"]) if c.get("source_page") else None,
                source_excerpt=str(c.get("source_excerpt", ""))[:500],
            )
        )

    logger.info(f"Extracted {len(candidates)} candidates after dedup.")
    return {
        "candidates": candidates,
        "extract_raw": "",  # Could store full LLM output if needed for debugging
    }
