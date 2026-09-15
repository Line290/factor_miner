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
    messages_token_estimate,
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


COMPRESS_PROMPT = """你是会话摘要器。请把下面这段 Agent 历史对话压缩为结构化摘要，必须保留：
1. 用户任务目标；
2. 已完成的动作与关键工具结果（数据、因子、代码、指标）；
3. 尚未完成的事项 / 待办；
4. 任何后续可能用到的数字与结论。

要求信息密度高、不遗漏关键事实，直接输出摘要文本，不要解释。"""


def _token_budget(cfg: AppConfig) -> int:
    return int(cfg.agent.context_window_tokens * cfg.agent.messages_max_tokens_ratio)


def _over_token_budget(msgs: list[dict], cfg: AppConfig) -> bool:
    if not msgs:
        return False
    return messages_token_estimate(msgs) > _token_budget(cfg)


def _compress_messages(msgs: list[dict], llm: LLMClient, cfg: AppConfig) -> list[dict] | None:
    """把中间轮次压缩为一条 system 摘要，保留首条 system 与最近 KEEP_RECENT 条消息。

    返回 None 表示不触发。
    """
    KEEP_RECENT = 6  # 最近 6 条（约 2~3 轮 assistant+tool）保持原样
    if len(msgs) <= KEEP_RECENT + 2:
        return None
    head = msgs[:1]          # 首条 system（角色提示）
    recent = msgs[-KEEP_RECENT:]
    to_compress = msgs[1:-KEEP_RECENT]
    if not to_compress:
        return None

    payload = json.dumps(to_compress, ensure_ascii=False)
    try:
        summary = llm.chat_messages(
            [
                {"role": "system", "content": COMPRESS_PROMPT},
                {"role": "user", "content": f"历史对话（JSON）：\n{payload}"},
            ],
            node="compress",
            temperature=0.0,
        ).strip()
    except Exception as e:
        logger.warning(f"[compress] 摘要生成失败，跳过压缩: {e}")
        return None

    # 摘要本身也要截断，防止压缩后仍超预算
    budget = _token_budget(cfg)
    max_summary_chars = max(200, int(budget * 0.3) * 3)  # ~预算的 30%（按 3 字符/token 粗估）
    if len(summary) > max_summary_chars:
        half = (max_summary_chars - 40) // 2
        summary = summary[:half] + "\n…[摘要截断]…\n" + summary[-half:]

    summary_msg = {"role": "system", "content": f"[历史会话摘要]\n{summary}"}
    return head + [summary_msg] + recent


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
        # token 预算监控（MA7）：超预算时由路由触发 compress
        est = messages_token_estimate(msgs + results)
        budget = _token_budget(cfg)
        if est > budget:
            logger.warning(f"[tools] 消息栈估算 {est} token > 预算 {budget}，准备压缩")
        return {
            "messages": results,
            "tool_calls_count": state.get("tool_calls_count", 0) + len(calls),
        }

    def compress_node(state: AgentSessionState) -> dict:
        msgs = list(state.get("messages") or [])
        new_msgs = _compress_messages(msgs, llm, cfg)
        if new_msgs is None:
            return {"messages": []}
        logger.info(f"[compress] 消息 {len(msgs)} → {len(new_msgs)} 条（摘要替换中间轮次）")
        return {"messages": {"__replace__": True, "messages": new_msgs}}

    def finalize_node(state: AgentSessionState) -> dict:
        msgs = state.get("messages") or []
        final = ""
        for m in reversed(msgs):
            if m.get("role") == "assistant" and not m.get("tool_calls"):
                final = m.get("content") or ""
                break
        rounds = state.get("agent_rounds", 0)
        n_calls = state.get("tool_calls_count", 0)
        logger.info(
            f"[finalize] rounds={rounds} tool_calls={n_calls} answer_len={len(final)}"
        )
        return {
            "finished_at": datetime.now(),
            "final_answer": final,
            "agent_rounds": rounds,
            "tool_calls_count": n_calls,
        }

    def route_after_agent(state: AgentSessionState) -> str:
        if state.get("agent_rounds", 0) >= cfg.agent.max_agent_rounds:
            logger.warning(f"[route] 达到最大轮数 {cfg.agent.max_agent_rounds}，强制收尾")
            return "finalize"
        msgs = state.get("messages") or []
        last = msgs[-1] if msgs else {}
        if last.get("tool_calls"):
            return "tools"
        return "finalize"

    def route_after_tools(state: AgentSessionState) -> str:
        # MA8: 工具执行后消息栈超 token 预算 → 先压缩再回 agent
        if _over_token_budget(state.get("messages") or [], cfg):
            return "compress"
        return "agent"

    g = StateGraph(AgentSessionState)
    g.add_node("agent", agent_node)
    g.add_node("tools", tools_node)
    g.add_node("compress", compress_node)
    g.add_node("finalize", finalize_node)
    g.set_entry_point("agent")
    g.add_conditional_edges("agent", route_after_agent, {
        "tools": "tools",
        "finalize": "finalize",
    })
    g.add_conditional_edges("tools", route_after_tools, {
        "compress": "compress",
        "agent": "agent",
    })
    g.add_edge("compress", "agent")
    g.add_edge("finalize", END)

    ckpt_path = Path(cfg.persistence.run_root).parent / "checkpoints.sqlite"
    ckpt_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(ckpt_path), check_same_thread=False)
    serde = NumpySafeSerializer(
        allowed_msgpack_modules=[("src.models", "MaterialMeta"), ("src.models", "CandidateRecord")]
    )
    checkpointer = SqliteSaver(conn, serde=serde)
    return g.compile(checkpointer=checkpointer)
