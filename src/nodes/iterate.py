"""Iterate node: LLM rewrites candidate based on fine-filter feedback."""
from __future__ import annotations

from loguru import logger

from ..config import AppConfig
from ..llm import LLMClient
from ..models import CandidateRecord
from ..prompts import load_prompt
from ..tools.business_rule import BusinessRules
from ..tools.data_schema import DataSchema


def iterate_node(
    state: dict,
    *,
    cfg: AppConfig,
    llm: LLMClient,
    data_schema: DataSchema,
    business_rules: BusinessRules,
) -> dict:
    c: CandidateRecord = CandidateRecord(**state["candidate"])

    user_msg = f"""原因子：
- name: {c.name}
- motivation: {c.motivation}
- logic_desc: {c.logic_desc}
- formula_draft: {c.formula_draft}

未通过原因：
{c.fine_feedback}

可用数据字段：
{data_schema.summary_for_llm()}

业务规则：
{business_rules.summary_for_llm()}

请修改 logic_desc / formula_draft（必要时微调 motivation），绕过未通过原因。"""

    try:
        resp = llm.chat_json(load_prompt("iterate_system"), user_msg, node="iterate")
        c.name = str(resp.get("name", c.name))
        c.motivation = str(resp.get("motivation", c.motivation))
        c.logic_desc = str(resp.get("logic_desc", c.logic_desc))
        c.formula_draft = str(resp.get("formula_draft", c.formula_draft))
        logger.info(f"Iterated {c.candidate_id} → {c.name}")
    except Exception as e:
        logger.warning(f"Iterate failed for {c.candidate_id}: {e}")
        c.fine_feedback = f"iterate_error: {e}"

    return {"candidate": c.model_dump()}
