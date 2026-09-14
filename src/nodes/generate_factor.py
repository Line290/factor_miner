"""GenerateFactor node: turn candidate draft into formula_latex + python_code."""
from __future__ import annotations

import ast
import json
from pathlib import Path

from loguru import logger

from ..config import AppConfig
from ..llm import LLMClient
from ..models import CandidateRecord
from ..prompts import load_prompt
from ..tools.data_schema import DataSchema


def _extract_df_fields(code: str) -> list[str]:
    """AST-scan for df["xxx"] or df.xxx accesses."""
    fields: set[str] = set()
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    for node in ast.walk(tree):
        # df["close_adj"]
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
            if node.value.id == "df":
                if isinstance(node.slice, ast.Constant):
                    fields.add(str(node.slice.value))
        # df.close_adj
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id == "df":
                fields.add(node.attr)
    return sorted(fields)


def generate_factor_node(
    state: dict,
    *,
    cfg: AppConfig,
    llm: LLMClient,
    data_schema: DataSchema,
) -> dict:
    c = CandidateRecord(**state["candidate"])

    # Load PIT rules
    pit_rules = Path(cfg.code_generation.pct_rules_path).read_text(encoding="utf-8")

    system = load_prompt("generate_factor_system", PIT_RULES=pit_rules)

    user_msg = f"""候选因子：
- name: {c.name}
- motivation: {c.motivation}
- logic_desc: {c.logic_desc}
- formula_draft: {c.formula_draft}

数据可得性检查已确认以下字段可用（请优先使用这些字段）：
{c.fine_checks.get('data_avail', {}).get('required_fields', [])}

完整数据字典：
{data_schema.summary_for_llm()}"""

    try:
        resp = llm.chat_json(system, user_msg, node="generate_factor")
        c.formula_latex = str(resp.get("formula_latex", ""))
        c.python_code = str(resp.get("python_code", ""))
        raw_fields = list(resp.get("required_fields", []))
        ast_fields = _extract_df_fields(c.python_code)
        merged: list[str] = []
        for f in raw_fields + ast_fields:
            if f not in merged:
                merged.append(f)
        c.required_fields, unknown = data_schema.filter_known(merged)
        if unknown:
            logger.warning(f"{c.candidate_id} 剔除非法 required_fields: {unknown}")

        logger.info(f"Generated code for {c.candidate_id}, "
                     f"required_fields={c.required_fields}")
    except Exception as e:
        logger.error(f"GenerateFactor failed for {c.candidate_id}: {e}")
        c.final_error = f"generate_factor_error: {e}"

    return {"candidate": c.model_dump()}
