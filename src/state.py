"""LangGraph State definition."""
from __future__ import annotations

from datetime import datetime
from operator import add
from typing import Annotated, TypedDict

from .models import CandidateRecord, MaterialMeta


class MinerState(TypedDict, total=False):
    # Input
    material_path: str
    run_id: str

    # Ingest
    material: MaterialMeta
    material_text: str

    # Extract
    candidates: list[CandidateRecord]
    extract_raw: str

    # Coarse
    coarse_done: bool

    # Error collection
    errors: Annotated[list[str], add]
    started_at: datetime
    finished_at: datetime
