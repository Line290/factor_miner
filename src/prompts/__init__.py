"""Prompt loader: read system prompt templates from files."""
from __future__ import annotations

from pathlib import Path

PROMPT_DIR = Path(__file__).resolve().parent


def load_prompt(name: str, **kwargs: str) -> str:
    """Load a prompt .txt file and replace {{key}} placeholders.

    Example:
        load_prompt("coarse_judge_system", DIMENSIONS="- novelty: ...")
    """
    path = PROMPT_DIR / f"{name}.txt"
    text = path.read_text(encoding="utf-8").strip()
    for k, v in kwargs.items():
        text = text.replace(f"{{{{{k}}}}}", v)
    return text
