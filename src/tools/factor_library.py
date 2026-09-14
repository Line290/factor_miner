"""Factor library: load index, describe factors for novelty check."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel


class FactorMeta(BaseModel):
    id: str
    name: str
    category: str
    logic_desc: str
    formula: str
    pit_note: str = ""
    values_path: str | None = None


@dataclass
class NoveltyCheckResult:
    passed: bool
    matched_factor_id: str | None
    reason: str


class FactorLibrary:
    def __init__(self, index_path: str | Path):
        self.index_path = Path(index_path)
        with open(self.index_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        self.factors: list[FactorMeta] = [FactorMeta(**x) for x in raw.get("factors", [])]

    def describe_for_llm(self) -> str:
        lines = []
        for f in self.factors:
            lines.append(f"- id={f.id} | name={f.name} | category={f.category}")
            lines.append(f"  logic: {f.logic_desc}")
            lines.append(f"  formula: {f.formula}")
        return "\n".join(lines)

    def __len__(self) -> int:
        return len(self.factors)
