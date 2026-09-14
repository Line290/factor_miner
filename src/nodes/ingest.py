"""Ingest node: read PDF/JSON into plain text + MaterialMeta."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from loguru import logger

from ..models import MaterialMeta
from ..state import MinerState


def _gen_run_id(path: str) -> str:
    stem = Path(path).stem.replace(" ", "_")[:40]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{ts}__{stem}"


def _parse_pdf(path: str) -> tuple[str, int]:
    import pdfplumber

    pages_text: list[str] = []
    with pdfplumber.open(path) as pdf:
        n = len(pdf.pages)
        for i, page in enumerate(pdf.pages, start=1):
            txt = page.extract_text() or ""
            pages_text.append(f"<<<PAGE {i}>>>\n{txt}")
    return "\n\n".join(pages_text), n


def _flatten_roadshow_json(path: str) -> str:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    segments = data if isinstance(data, list) else data.get("segments", [])
    lines = []
    for item in segments:
        if isinstance(item, dict):
            speaker = item.get("speaker", item.get("role", ""))
            content = item.get("content", item.get("text", ""))
            lines.append(f"[{speaker}] {content}")
        else:
            lines.append(str(item))
    return "\n".join(lines)


def ingest_node(state: MinerState) -> dict:
    path = state["material_path"]
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Material not found: {path}")

    suffix = p.suffix.lower()
    if suffix == ".pdf":
        text, pages = _parse_pdf(path)
        mtype = "pdf"
    elif suffix == ".json":
        text = _flatten_roadshow_json(path)
        pages = None
        mtype = "json"
    else:
        raise ValueError(f"Unsupported material type: {suffix} (use .pdf or .json)")

    run_id = state.get("run_id") or _gen_run_id(path)
    material = MaterialMeta(
        run_id=run_id,
        path=str(p.resolve()),
        type=mtype,  # type: ignore[arg-type]
        title=p.stem,
        pages=pages,
        loaded_at=datetime.now(),
    )
    logger.info(f"Ingested {path} ({mtype}, {len(text)} chars, {pages} pages)")
    return {
        "material": material,
        "material_text": text,
        "run_id": run_id,
        "started_at": datetime.now(),
    }
