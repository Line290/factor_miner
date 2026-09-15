"""MA4: Agentic session graph — Claude Code-style ReAct loop.

User → agent(LLM, 可能返回 tool_calls) → tools(批量执行) → agent(继续/结束) → finalize

- 手写 StateGraph（非 create_react_agent），消息模型为 OpenAI 原生 dict；
- 轮数保护：agent_rounds >= cfg.agent.max_agent_rounds 强制收尾；
- checkpointer：复用 checkpoints.sqlite（thread_id = 会话 ID，天然支持中断恢复）。
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from loguru import logger
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, StateGraph

from .agent_state import (
    AgentSessionState,
    human_message,
    tool_message,
    validate_tool_messages,
)
from .agent_tools import ToolContext, dispatch, tool_schemas
from .config import AppConfig
from .llm import LLMClient
from .models import CandidateRecord, MaterialMeta
from .persistence import RunRecorder
from .tools.business_rule import BusinessRules
from .tools.data_schema import DataSchema
from .tools.factor_library import FactorLibrary
from .tools.serde_numpy import NumpySafeSerializer

AGENT_SYSTEM_PROMPT = """你是 Factor Miner Agent，一个自主的量化因子挖掘智能体。

任务：从输入材料（研报 / 论文 / 路演纪要）或用户任务中提炼可落地的量化因子，
自主调用工具完成完整链路：
读材料 → 查数据字典 / 因子库 / 业务规则 → 生成因子代码 → 沙箱执行 → 回测 → 入库。

约束：
- PIT 合规：禁止未来函数（shift(-N)、rolling(center=True)）；信号 T 日、T+1 成交。
- 字段只能来自 query_data_schema；date/code 面板索引列恒有。
- 因子代码必须定义 def compute(df) -> pd.Series，返回与 df 行数一致的序列；
  组内运算用 groupby(...).transform，不要用聚合。
- 与因子库相关性高（>0.7）的因子不要入库。
- 每次调用工具后先观察返回结果，再决定下一步；任务完成即直接输出最终结论，
  不要做无意义的多余工具调用。
"""


def _load_domain_tools(cfg: AppConfig):
    data_schema_path = cfg.fine_filter.data_availability.data_schema_path
    factor_library = FactorLibrary(data_schema_path.parent / "factor_library_index.yaml")
    data_schema = DataSchema(data_schema_path)
    business_rules = BusinessRules(cfg.fine_filter.business_rules.rules_path)
    data_dir = Path(cfg.persistence.run_root).parent / "parquet"
    logger.info(
        f"Agent tools loaded: {len(factor_library)} library factors, "
        f"{len(data_schema.fields)} data fields, {len(business_rules.rules)} rules"
    )
    return factor_library, data_schema, business_rules, data_dir


def build_agent_graph(cfg: AppConfig, llm: LLMClient):
    """Build the compiled agentic session graph (ReAct loop)."""
    factor_library, data_schema, business_rules, data_dir = _load_domain_tools(cfg)
    recorders: dict[str, RunRecorder] = {}

    def _make_ctx(state: AgentSessionState) -> ToolContext:
        thread_id = state.get("thread_id", "unknown")
        run_dir = Path(cfg.persistence.run_root) / thread_id
        recorder = recorders.get(thread_id)
        if recorder is None and state.get("material"):
            material = MaterialMeta(**state["material"])
            recorder = RunRecorder(run_id=thread_id, cfg=cfg, material=material)
            recorders[thread_id] = recorder
        return ToolContext(
            cfg=cfg,
            thread_id=thread_id,
            run_dir=run_dir,
            data_dir=data_dir,
            recorder=recorder,
            material_text=state.get("material_text"),
            factor_library=factor_library,
            data_schema=data_schema,
            business_rules=business_rules,
        )

    def agent_node(state: AgentSessionState) -> dict:
        msgs = list(state.get("messages") or [])
        seeded = False
        if not msgs:
            # 首轮：注入 system 提示 + 用户任务，并整体写回消息栈（保证会话完整性）
            msgs = [
                {"role": "system", "content": AGENT_SYSTEM_PROMPT},
                human_message(state.get("task") or ""),
            ]
            seeded = True
        resp = llm.chat_message(msgs, tools=tool_schemas(), node="agent")
        rounds = state.get("agent_rounds", 0) + 1
        n_calls = len(resp.get("tool_calls") or [])
        logger.info(f"[agent] round={rounds} tool_calls={n_calls}")
        if seeded:
            return {"messages": msgs + [resp], "agent_rounds": rounds}
        return {"messages": [resp], "agent_rounds": rounds}

    def tools_node(state: AgentSessionState) -> dict:
        msgs = list(state.get("messages") or [])
        if not msgs:
            return {"messages": [], "errors": ["tools 节点触发但消息栈为空"]}
        last = msgs[-1]
        calls = last.get("tool_calls") or []
        ctx = _make_ctx(state)
        results: list[dict] = []
        for call in calls:
            call_id = call.get("id")
            fn = call.get("function") or {}
            name = fn.get("name", "")
            try:
                args = json.loads(fn.get("arguments") or "{}")
                if not isinstance(args, dict):
                    raise ValueError(f"arguments 不是 JSON 对象: {args!r}")
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"[tools] {name} arguments 解析失败: {e}")
                results.append(tool_message(
                    call_id,
                    json.dumps({"error": f"arguments 解析失败: {e}"}, ensure_ascii=False),
                ))
                continue
            logger.info(f"[tools] {name}({json.dumps(args, ensure_ascii=False)[:200]})")
            out = dispatch(name, args, ctx, truncate_chars=cfg.agent.tool_output_truncate_chars)
            results.append(tool_message(call_id, out))

        problems = validate_tool_messages(msgs + results)
        if problems:
            logger.warning(f"[tools] 消息栈校验问题: {problems}")
        return {
            "messages": results,
            "tool_calls_count": state.get("tool_calls_count", 0) + len(calls),
        }

    def finalize_node(state: AgentSessionState) -> dict:
        msgs = state.get("messages") or []
        final = ""
        for m in reversed(msgs):
            if m.get("role") == "assistant" and not m.get("tool_calls"):
                final = m.get("content") or ""
                break
        logger.info(
            f"[finalize] rounds={state.get('agent_rounds')} "
            f"tool_calls={state.get('tool_calls_count')} answer_len={len(final)}"
        )
        return {"finished_at": datetime.now(), "final_answer": final}

    def route_after_agent(state: AgentSessionState) -> str:
        if state.get("agent_rounds", 0) >= cfg.agent.max_agent_rounds:
            logger.warning(f"[route] 达到最大轮数 {cfg.agent.max_agent_rounds}，强制收尾")
            return "finalize"
        msgs = state.get("messages") or []
        last = msgs[-1] if msgs else {}
        if last.get("tool_calls"):
            return "tools"
        return "finalize"

    g = StateGraph(AgentSessionState)
    g.add_node("agent", agent_node)
    g.add_node("tools", tools_node)
    g.add_node("finalize", finalize_node)
    g.set_entry_point("agent")
    g.add_conditional_edges("agent", route_after_agent, {
        "tools": "tools",
        "finalize": "finalize",
    })
    g.add_edge("tools", "agent")
    g.add_edge("finalize", END)

    ckpt_path = Path(cfg.persistence.run_root).parent / "checkpoints.sqlite"
    ckpt_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(ckpt_path), check_same_thread=False)
    serde = NumpySafeSerializer(
        allowed_msgpack_modules=[("src.models", "MaterialMeta"), ("src.models", "CandidateRecord")]
    )
    checkpointer = SqliteSaver(conn, serde=serde)
    return g.compile(checkpointer=checkpointer)
