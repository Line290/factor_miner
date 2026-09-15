"""MA3: Agent tool registry.

将现有领域能力（沙箱执行 / 因子库 / 数据字典 / 业务规则 / 回测 / 入库 / 读材料）
封装为 OpenAI tools 格式的注册表，供 Agentic 会话的 agent 节点调用。

每个工具：schema（OpenAI tools 格式）+ 执行函数 ``fn(args: dict, ctx: ToolContext) -> Any``。
统一由 :func:`dispatch` 做异常包装与输出截断。
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from loguru import logger

from ..config import AppConfig
from ..models import CandidateRecord
from ..nodes.backtest import backtest_node
from ..nodes.ingest import _flatten_roadshow_json, _parse_pdf
from ..persistence import RunRecorder
from ..tools.business_rule import BusinessRules
from ..tools.code_sandbox import run_factor_code
from ..tools.data_schema import DataSchema
from ..tools.factor_library import FactorLibrary


@dataclass
class ToolContext:
    """工具执行上下文：由 build_agent_graph 一次性注入。"""
    cfg: AppConfig
    thread_id: str
    run_dir: Path
    data_dir: Path
    recorder: RunRecorder | None
    material_text: str | None
    factor_library: FactorLibrary
    data_schema: DataSchema
    business_rules: BusinessRules


ToolFn = Callable[[dict, ToolContext], Any]


def _schema(name: str, description: str, properties: dict, required: list[str] | None = None) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                **({"required": required} if required else {}),
            },
        },
    }


# ---------- 工具实现 ----------

def _read_material(args: dict, ctx: ToolContext) -> dict:
    text = ctx.material_text or ""
    if not text:
        return {"error": "当前会话没有加载材料（--material 未指定或加载失败）"}

    chunks = re.split(r"<<<PAGE (\d+)>>>", text)
    pages: list[dict] = []
    for i in range(1, len(chunks), 2):
        pages.append({"page": int(chunks[i]), "text": (chunks[i + 1] or "").strip()})
    if not pages:
        pages = [{"page": 1, "text": text.strip()}]

    page = args.get("page")
    if page is not None:
        for p in pages:
            if p["page"] == int(page):
                return {"page": p["page"], "total_pages": len(pages), "text": p["text"]}
        return {"error": f"第 {page} 页不存在", "total_pages": len(pages)}

    toc = "\n".join(f"[p{p['page']}] {p['text'][:120]}" for p in pages)
    return {"total_pages": len(pages), "目录": toc}


def _query_data_schema(args: dict, ctx: ToolContext) -> dict:
    fields = args.get("fields") or []
    if not fields:
        return {"summary": ctx.data_schema.summary_for_llm()}
    known, unknown = ctx.data_schema.filter_known(fields)
    chk = ctx.data_schema.check(fields)
    return {
        "known_fields": known,
        "unknown_fields": unknown,
        "all_available": chk.passed,
        "reason": chk.reason,
    }


def _query_factor_library(args: dict, ctx: ToolContext) -> dict:
    kw = (args.get("keywords") or "").strip().lower()
    if not kw:
        return {"count": len(ctx.factor_library), "factors": ctx.factor_library.describe_for_llm()}
    hits = [
        f for f in ctx.factor_library.factors
        if kw in f.name.lower() or kw in f.logic_desc.lower() or kw in f.formula.lower()
    ]
    if not hits:
        return {"count": 0, "note": f"无匹配关键词 {kw!r}", "hint": "可无参调用查看全量因子库"}
    lines = [f"- id={f.id} | name={f.name} | {f.logic_desc} | formula: {f.formula}" for f in hits]
    return {"count": len(hits), "factors": "\n".join(lines)}


def _query_business_rules(args: dict, ctx: ToolContext) -> dict:
    return {"rules": ctx.business_rules.summary_for_llm()}


def _run_factor_code(args: dict, ctx: ToolContext) -> dict:
    code = (args.get("code") or "").strip()
    required = args.get("required_fields") or []
    if not code:
        return {"error": "code 不能为空"}
    if not isinstance(required, list):
        return {"error": "required_fields 必须是字段名列表"}

    name = (args.get("name") or "factor").replace(" ", "_")[:30]
    ts = time.strftime("%H%M%S")
    out_path = ctx.run_dir / "factors" / f"agent_{ctx.thread_id[:8]}_{name}_{ts}.parquet"
    res = run_factor_code(
        code,
        required,
        data_dir=ctx.data_dir,
        output_path=out_path,
        python_bin=ctx.cfg.code_generation.python_bin,
        timeout_sec=ctx.cfg.code_generation.sandbox_timeout_sec,
    )
    return {
        "success": res.success,
        "values_path": res.values_path,
        "error": res.error,
        "stdout": res.stdout,
    }


def _run_backtest(args: dict, ctx: ToolContext) -> dict:
    vp = (args.get("factor_values_path") or "").strip()
    if not vp or not Path(vp).exists():
        return {"error": f"factor_values_path 不存在或为空: {vp!r}（先用 run_factor_code 产出因子值）"}
    c = CandidateRecord(
        candidate_id=f"agent_{ctx.thread_id[:8]}",
        name="agent_factor",
        motivation="", logic_desc="", formula_draft="",
        factor_values_path=str(Path(vp).resolve()),
    )
    try:
        out = backtest_node({"candidate": c.model_dump()}, cfg=ctx.cfg, run_dir=ctx.run_dir)
    except Exception as e:  # 回测数据缺失等场景不应中断会话
        logger.warning(f"run_backtest failed: {e}")
        return {"error": f"回测执行失败: {e}"}
    c2 = CandidateRecord(**out["candidate"])
    aa = ctx.cfg.backtest.auto_archive
    archived = (
        c2.ic is not None and c2.ir is not None
        and c2.ic >= aa.min_ic and c2.ir >= aa.min_ir
    )
    return {
        "ic": c2.ic,
        "ir": c2.ir,
        "status": c2.status,
        "report_path": c2.backtest_report_path,
        "archived": bool(archived),
        "note": f"归档阈值 IC>={aa.min_ic} 且 IR>={aa.min_ir}",
    }


def _save_factor(args: dict, ctx: ToolContext) -> dict:
    cand = args.get("candidate") or {}
    if not isinstance(cand, dict):
        return {"error": "candidate 必须是 JSON 对象"}
    required = ["name", "motivation", "logic_desc", "formula_draft"]
    missing = [k for k in required if not cand.get(k)]
    if missing:
        return {"error": f"candidate 缺少必填字段: {missing}"}
    if ctx.recorder is None:
        return {"error": "run recorder 未初始化"}

    c = CandidateRecord(
        candidate_id=cand.get("candidate_id") or f"agent_{ctx.thread_id[:8]}_{int(time.time())}",
        name=str(cand["name"]),
        motivation=str(cand["motivation"]),
        logic_desc=str(cand["logic_desc"]),
        formula_draft=str(cand["formula_draft"]),
        formula_latex=cand.get("formula_latex"),
        python_code=cand.get("python_code"),
        required_fields=list(cand.get("required_fields") or []),
        factor_values_path=cand.get("factor_values_path"),
        ic=cand.get("ic"),
        ir=cand.get("ir"),
        status="backtested" if cand.get("ic") is not None else "code_runnable",
    )
    ctx.recorder.flush_candidate(c)
    return {"saved_candidate_id": c.candidate_id, "run_record": str(ctx.recorder.path())}


# ---------- 注册表 ----------

# name -> (OpenAI tools schema, fn)
TOOL_SPECS: dict[str, tuple[dict, ToolFn]] = {
    "read_material": (
        _schema(
            "read_material",
            "读取当前会话输入材料（研报PDF/路演纪要JSON）的文本。无参数时返回各页目录（每页前 120 字）；指定 page 返回该页全文。",
            {"page": {"type": "integer", "description": "页码（1-based），不传则返回目录"}},
        ),
        _read_material,
    ),
    "query_data_schema": (
        _schema(
            "query_data_schema",
            "查询本地行情数据字典：可用字段、频率、口径、可推导字段、暂不可用字段。传 fields 可校验指定字段是否可得。",
            {
                "fields": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "要校验的字段名列表（可选）",
                }
            },
        ),
        _query_data_schema,
    ),
    "query_factor_library": (
        _schema(
            "query_factor_library",
            "查询本地因子库（已沉淀因子），用于新颖性自查：判断你的新因子是否与库内因子重复/高度相关。",
            {"keywords": {"type": "string", "description": "关键词（可选），按名称/逻辑/公式模糊匹配"}},
        ),
        _query_factor_library,
    ),
    "query_business_rules": (
        _schema(
            "query_business_rules",
            "查询业务合规硬规则（如禁止的因子方向），确保新因子不违反。",
            {},
        ),
        _query_business_rules,
    ),
    "run_factor_code": (
        _schema(
            "run_factor_code",
            "在隔离沙箱中执行因子计算代码（PIT 合规：禁 import/文件读/未来函数）。compute(df) 必须返回与 df 行数一致的 pd.Series。成功后返回因子值 parquet 路径。",
            {
                "code": {"type": "string", "description": "Python 代码，必须定义 def compute(df) -> pd.Series"},
                "required_fields": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "代码用到的数据字段名（date/code 恒有，可不列）",
                },
                "name": {"type": "string", "description": "因子名（可选，用于命名输出文件）"},
            },
            required=["code", "required_fields"],
        ),
        _run_factor_code,
    ),
    "run_backtest": (
        _schema(
            "run_backtest",
            "对因子值 parquet（run_factor_code 的返回 values_path）跑截面 Rank IC/IR 回测，达标（IC/IR 阈值）自动入库。",
            {
                "factor_values_path": {
                    "type": "string",
                    "description": "run_factor_code 返回的 values_path",
                }
            },
            required=["factor_values_path"],
        ),
        _run_backtest,
    ),
    "save_factor": (
        _schema(
            "save_factor",
            "将因子（名称/动机/逻辑/公式/代码/回测指标）写入本次运行留档。IC/IR 达标时建议先用 run_backtest（会自动入库）。",
            {
                "candidate": {
                    "type": "object",
                    "description": "因子对象：必填 name/motivation/logic_desc/formula_draft；可选 formula_latex/python_code/required_fields/factor_values_path/ic/ir",
                }
            },
            required=["candidate"],
        ),
        _save_factor,
    ),
}


def tool_schemas() -> list[dict]:
    """OpenAI tools 格式的完整工具列表（传给 LLM）。"""
    return [spec[0] for spec in TOOL_SPECS.values()]


def dispatch(name: str, args: dict, ctx: ToolContext, truncate_chars: int = 8000) -> str:
    """执行工具：异常包装 + JSON 序列化 + 输出截断。返回可回填 tool 消息的字符串。"""
    spec = TOOL_SPECS.get(name)
    if spec is None:
        return json.dumps({"error": f"未知工具: {name}"}, ensure_ascii=False)
    fn = spec[1]
    try:
        out = fn(args, ctx)
        if isinstance(out, str):
            text = out
        else:
            text = json.dumps(out, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error(f"tool {name} 执行异常: {e}")
        text = json.dumps({"error": f"{type(e).__name__}: {e}"}, ensure_ascii=False)
    if len(text) > truncate_chars:
        half = (truncate_chars - 40) // 2
        text = text[:half] + "\n…[工具输出已截断]…\n" + text[-half:]
    return text
