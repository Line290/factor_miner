"""CLI entrypoint（Agentic 模式 = 唯一入口，MA9 起旧流水线入口已退役）。

Claude Code 式长程会话:
    python -m src.main --task "从研报提炼 2 个因子" [--material path]
    python -m src.main --resume <thread_id>
    python -m src.main --list-sessions

旧流水线 DAG（确定性 pipeline）已在 MA9 退役：其节点逻辑已迁移为
Agentic 工具（read_material/query_*/run_*/save_factor），main 分支保留旧实现可回退。
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

from .agent_graph import build_agent_graph
from .config import load_config
from .llm import LLMClient
from .nodes.ingest import ingest_file
from .session_store import SessionStore


def _gen_session_id() -> str:
    return "sess_" + datetime.now().strftime("%Y%m%d_%H%M%S")


def _print_session_table(store: SessionStore) -> None:
    sessions = store.list_sessions(limit=30)
    if not sessions:
        print("（暂无会话）")
        return
    print(f"{'thread_id':<24}{'状态':<7}{'轮数':<5}{'工具':<5}{'更新时间':<21}任务")
    print("-" * 96)
    for s in sessions:
        task = s.task[:38].replace("\n", " ")
        print(f"{s.thread_id:<24}{s.status:<7}{s.agent_rounds:<5}{s.tool_calls_count:<5}{s.updated_at:<21}{task}")


def _print_node(node: str, update: dict) -> None:
    """节点级流式输出：agent → tools → agent 过程实时可见。"""
    if node == "agent":
        msgs = update.get("messages") or []
        if not msgs:
            return
        msg = msgs[-1]
        if msg.get("tool_calls"):
            names = ", ".join(tc["function"]["name"] for tc in msg["tool_calls"])
            print(f"  ⟳ agent(#{update.get('agent_rounds', '?')}) → 调用: {names}")
        else:
            content = (msg.get("content") or "").strip()
            print(f"  ⏹ agent: {content[:160]}")
    elif node == "tools":
        for m in update.get("messages", []):
            print(f"  ⚙ {m.get('tool_call_id', '?')[:8]} → {m.get('content', '')[:160]}")


def run_agentic_session(
    cfg,
    llm,
    *,
    task: str | None = None,
    material_path: str | None = None,
    resume: str | None = None,
) -> dict:
    """Agentic 会话：新会话或恢复，图流式执行，结束后写回会话元数据。"""
    store = SessionStore(cfg.persistence.session_store_path)
    graph = build_agent_graph(cfg, llm)

    if resume:
        meta = store.get(resume)
        if meta is None:
            raise ValueError(f"会话不存在: {resume}（可用 --list-sessions 查看）")
        thread_id = resume
        initial = {"thread_id": thread_id}
        print(f"恢复会话: {thread_id}（{meta.status}，历史 {meta.agent_rounds} 轮 / {meta.tool_calls_count} 工具调用）")
    else:
        if not task:
            raise ValueError("agentic 新会话需要 --task（或 --resume 恢复已有会话）")
        thread_id = _gen_session_id()
        material_dict = None
        material_text = None
        if material_path:
            mat, text = ingest_file(material_path)
            material_dict = mat.model_dump()
            material_text = text
        initial = {
            "thread_id": thread_id,
            "task": task,
            "material": material_dict,
            "material_text": material_text,
        }
        store.create(thread_id, task=task, material_path=material_path)
        print(f"新会话: {thread_id}")

    config = {"configurable": {"thread_id": thread_id}}
    final: dict = {}
    for chunk in graph.stream(initial, config=config, stream_mode="updates"):
        for node, update in chunk.items():
            _print_node(node, update)
            if node == "finalize":
                final = update

    store.finalize(
        thread_id,
        final_answer=final.get("final_answer", ""),
        agent_rounds=final.get("agent_rounds", 0),
        tool_calls_count=final.get("tool_calls_count", 0),
    )
    return {"thread_id": thread_id, **final}


def main() -> int:
    parser = argparse.ArgumentParser(description="Factor Miner Agent（Agentic 会话，Claude Code 式 ReAct）")
    parser.add_argument("--task", default=None, help="任务描述（新会话必填）")
    parser.add_argument("--material", default=None, help="输入材料 (.pdf/.json)")
    parser.add_argument("--config", default="configs/default.yaml", help="Path to YAML config")
    parser.add_argument("--resume", default=None, help="恢复会话 thread_id")
    parser.add_argument("--list-sessions", action="store_true", help="列出历史会话")
    args = parser.parse_args()

    load_dotenv()
    logger.remove()
    logger.add(sys.stderr, level="INFO")

    cfg = load_config(args.config)
    llm = LLMClient(cfg.llm)

    if args.list_sessions:
        _print_session_table(SessionStore(cfg.persistence.session_store_path))
        return 0
    try:
        out = run_agentic_session(cfg, llm, task=args.task,
                                  material_path=args.material, resume=args.resume)
    except (ValueError, FileNotFoundError) as e:
        print(f"错误: {e}")
        return 1
    print("\n==== 最终答案 ====")
    print(out.get("final_answer", "") or "（无最终输出，可能被轮数上限截停）")
    print(f"\n[会话 {out['thread_id']} 完成] rounds={out.get('agent_rounds', 0)} tools={out.get('tool_calls_count', 0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
