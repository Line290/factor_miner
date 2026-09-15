"""CodeFix node: LLM fixes factor code based on sandbox error."""
from __future__ import annotations

import json
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

    # Build true multi-turn messages: system + (user request, assistant code, user feedback) per round
    messages: list[dict] = [{"role": "system", "content": system}]

    for step in c.code_fix_history:
        if step.python_code:
            messages.append({"role": "assistant", "content": json.dumps({
                "python_code": step.python_code,
            }, ensure_ascii=False)})
        if step.success:
            messages.append({"role": "user", "content": "代码执行成功。"})
        else:
            messages.append({"role": "user", "content": f"代码执行失败，报错：\n{step.error or 'n/a'}"})

    # Current round request
    messages.append({"role": "user", "content": f"""请修复代码。

当前代码：
```python
{c.python_code}
```

最新报错：
{c.code_last_error}

可用字段：
{data_schema.summary_for_llm()}

注意：不要重复之前已经失败的写法。"""})

    try:
        raw = llm.chat_messages(messages, node="code_fix", json_mode=True)
        resp = llm._parse_json(raw)
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
