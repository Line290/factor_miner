"""Data schema: load field catalog, check required fields availability."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel


class FieldMeta(BaseModel):
    name: str
    dtype: str
    freq: str
    desc: str
    pit_note: str = ""
    unit: str = ""


class DerivedField(BaseModel):
    name: str
    formula: str
    desc: str


class UnavailableField(BaseModel):
    name: str
    reason: str = ""


@dataclass
class DataAvailResult:
    passed: bool
    required_fields: list[str]
    missing_fields: list[str]
    derivable_fields: list[str]
    fatal_missing: list[str]   # 在 unavailable 列表里，迭代也没用
    reason: str


class DataSchema:
    # 面板索引列，market.parquet 恒有（gen_mock_data 以 date/code 为 MultiIndex），
    # 但不在数据字典 fields 里，校验时需放行
    PANEL_INDEX_FIELDS = ("date", "code")

    def __init__(self, schema_path: str | Path):
        self.schema_path = Path(schema_path)
        with open(self.schema_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        self.fields: dict[str, FieldMeta] = {
            x["name"]: FieldMeta(**x) for x in raw.get("fields", [])
        }
        self.derived: list[DerivedField] = [
            DerivedField(**x) for x in raw.get("derived", [])
        ]
        self.unavailable: dict[str, str] = {
            x["name"]: x.get("reason", "") for x in raw.get("unavailable", [])
        }
        # Build a set of all known field names (direct + derived outputs)
        self._known: set[str] = set(self.fields.keys())
        for d in self.derived:
            self._known.add(d.name)
            # Also register input fields used in derived formulas
            # (lightweight: split on operators)
            for tok in d.formula.replace("(", " ").replace(")", " ").split():
                tok = tok.strip()
                if tok and tok.isidentifier():
                    self._known.add(tok)

    def summary_for_llm(self) -> str:
        lines = ["可用字段："]
        lines.append("- date, code: 面板索引列（交易日、证券代码），每次都会随 df 传入")
        for name, meta in list(self.fields.items())[:40]:
            lines.append(f"- {name}: {meta.desc}")
        if len(self.fields) > 40:
            lines.append(f"... 共 {len(self.fields)} 个字段")
        if self.derived:
            lines.append("\n可推导字段：")
            for d in self.derived:
                lines.append(f"- {d.name} = {d.formula}  ({d.desc})")
        if self.unavailable:
            lines.append("\n暂不可用字段：")
            for name, reason in self.unavailable.items():
                lines.append(f"- {name}: {reason}")
        return "\n".join(lines)

    def filter_known(self, fields: list[str]) -> tuple[list[str], list[str]]:
        """按数据字典过滤字段，返回 (已知, 未知)。

        required_fields 最终会作为 parquet 的 columns 过滤条件传入沙箱，
        LLM 返回或 AST 扫描（如把 df.index 当字段）混入的非列名必须剔除。
        """
        known = [f for f in fields
                 if f in self.fields or f in self.PANEL_INDEX_FIELDS]
        unknown = [f for f in fields
                   if f not in self.fields and f not in self.PANEL_INDEX_FIELDS]
        return known, unknown

    def check(self, required: list[str]) -> DataAvailResult:
        missing: list[str] = []
        derivable: list[str] = []
        fatal: list[str] = []
        for fld in required:
            fld = fld.strip().lower()
            if not fld:
                continue
            if fld in self.fields:
                continue
            if fld in self.unavailable:
                missing.append(f"{fld}（{self.unavailable[fld]}）")
                fatal.append(fld)
                continue
            if any(d.name.lower() == fld for d in self.derived):
                derivable.append(fld)
                continue
            missing.append(fld)

        passed = len(missing) == 0
        if passed:
            reason = "所有字段均可用"
            if derivable:
                reason += f"（其中 {len(derivable)} 个由已有字段推导）"
        else:
            reason = f"缺失字段: {', '.join(missing)}"
            if fatal:
                reason += f" [致命: {', '.join(fatal)} 不可用]"
        return DataAvailResult(
            passed=passed,
            required_fields=required,
            missing_fields=missing,
            derivable_fields=derivable,
            fatal_missing=fatal,
            reason=reason,
        )
