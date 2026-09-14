"""CodeFix node: LLM fixes factor code based on sandbox error."""
from __future__ import annotations

from pathlib import Path

from loguru import logger

from ..config import AppConfig
from ..llm import LLMClient
from ..models import CandidateRecord
from ..prompts import load_prompt
from ..tools.data_schema import DataSchema


def code_fix_node(
    state: dict,
    *,
    cfg: AppConfig,
    llm: LLMClient,
    data_schema: DataSchema,
) -> dict:
    c = CandidateRecord(**state["candidate"])

    pit_rules = Path(cfg.code_generation.pct_rules_path).read_text(encoding="utf-8")
    system = load_prompt("code_fix_system", PIT_RULES=pit_rules)

    user_msg = f"""上一次代码执行失败：

【报错信息】
{c.code_last_error}

【原代码】
{c.python_code}

【可用字段】
{data_schema.summary_for_llm()}

请修复代码，保持因子逻辑不变。"""

    try:
        resp = llm.chat_json(system, user_msg, node="code_fix")
        c.python_code = str(resp.get("python_code", c.python_code))
        new_fields = list(resp.get("required_fields", []))
        for f in new_fields:
            if f not in c.required_fields:
                c.required_fields.append(f)
        c.required_fields, unknown = data_schema.filter_known(c.required_fields)
        if unknown:
            logger.warning(f"{c.candidate_id} 剔除非法 required_fields: {unknown}")
        logger.info(f"CodeFix round {c.code_fix_rounds}: {c.candidate_id}")
    except Exception as e:
        logger.error(f"CodeFix failed for {c.candidate_id}: {e}")
        c.code_last_error = f"code_fix_error: {e}"

    return {"candidate": c.model_dump()}
