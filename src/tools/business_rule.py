"""Business rules check: hard rules that reject certain factor directions."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel

from ..llm import LLMClient
from ..models import CandidateRecord
from ..prompts import load_prompt


class Rule(BaseModel):
    id: str
    name: str
    type: str = "semantic"
    desc: str
    match_keywords: list[str] = []
    severity: str = "hard"


@dataclass
class BizCheckResult:
    passed: bool
    violated: list[str]
    reason: str


class BusinessRules:
    def __init__(self, rules_path: str | Path):
        self.rules_path = Path(rules_path)
        with open(self.rules_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        self.rules: list[Rule] = [Rule(**x) for x in raw.get("rules", [])]

    def summary_for_llm(self) -> str:
        lines = []
        for r in self.rules:
            lines.append(f"- [{r.id}] {r.name}: {r.desc}")
        return "\n".join(lines)

    def check_keywords(self, c: CandidateRecord) -> list[str]:
        """Fast keyword pre-screen."""
        text = f"{c.logic_desc}\n{c.formula_draft}".lower()
        violated = []
        for r in self.rules:
            for kw in r.match_keywords:
                if kw.lower() in text:
                    violated.append(r.id)
                    break
        return violated

    def check_with_llm(self, c: CandidateRecord, llm: LLMClient) -> BizCheckResult:
        # 1. Keyword pre-screen
        violated = self.check_keywords(c)

        # 2. LLM semantic check (only for hard rules not already caught)
        rules_for_llm = [r for r in self.rules if r.id not in violated]
        if rules_for_llm:
            rule_lines = "\n".join(f"- [{r.id}] {r.desc}" for r in rules_for_llm)
            prompt = f"""你在判断一个新因子是否违反以下业务规则：
{rule_lines}

新因子：
- name: {c.name}
- logic_desc: {c.logic_desc}
- formula_draft: {c.formula_draft}

对每条规则，判断该因子是否违反（hard 规则违反即淘汰）。
严格输出 JSON：
{{"violated": ["<rule_id>", ...], "reason": "..."}}"""
            try:
                resp = llm.chat_json(
                    load_prompt("biz_check_system"),
                    prompt,
                    node="biz_check",
                )
                for rid in resp.get("violated", []):
                    if rid not in violated:
                        violated.append(rid)
            except Exception as e:
                # LLM 失败不阻塞，按已有的 keyword 结果走
                violated.append(f"llm_check_failed({e})")

        passed = len(violated) == 0
        if passed:
            reason = "未违反业务规则"
        else:
            names = {r.id: r.name for r in self.rules}
            reason = "违反: " + ", ".join(
                f"{rid}({names.get(rid, rid)})" for rid in violated
            )
        return BizCheckResult(passed=passed, violated=violated, reason=reason)
