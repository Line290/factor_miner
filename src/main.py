"""CLI entrypoint: python -m src.main --material <path>"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

from .config import load_config
from .graph import build_graph
from .llm import LLMClient
from .persistence import RunRecorder
from .state import MinerState


def _gen_run_id(path: str) -> str:
    stem = Path(path).stem.replace(" ", "_")[:40]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{ts}__{stem}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Single factor mining agent")
    parser.add_argument("--material", required=False, default=None,
                        help="Path to material (.pdf or .json)")
    parser.add_argument("--config", default="configs/default.yaml", help="Path to YAML config")
    parser.add_argument("--run-id", default=None, help="Override run id")
    parser.add_argument("--resume", default=None,
                        help="Resume a previous run by run_id (skips already-completed nodes)")
    args = parser.parse_args()

    load_dotenv()
    logger.remove()
    logger.add(sys.stderr, level="INFO")

    cfg = load_config(args.config)
    llm = LLMClient(cfg.llm)
    graph, holder = build_graph(cfg, llm)

    if args.resume:
        thread_id = args.resume
        # resume 时 ingest 被跳过，recorder 不会在图内创建；
        # 从已有 run_record.json 重建，供 save/extract 等节点续写
        holder["recorder"] = RunRecorder.resume(thread_id, cfg)
        logger.info(f"Resuming run: {thread_id}")
        final_state = graph.invoke(None, config={
            "configurable": {
                "thread_id": thread_id,
                "max_concurrency": cfg.robustness.max_concurrency,
            }
        })
    else:
        if not args.material:
            parser.error("--material is required for a new run")
        material_path = str(Path(args.material).resolve())
        thread_id = args.run_id or _gen_run_id(material_path)
        initial: MinerState = {"material_path": material_path, "run_id": thread_id}
        logger.info(f"Starting run: {thread_id}")
        final_state = graph.invoke(initial, config={
            "configurable": {
                "thread_id": thread_id,
                "max_concurrency": cfg.robustness.max_concurrency,
            }
        })

    recorder = holder.get("recorder")
    if recorder:
        recorder.finalize()
        logger.info(f"Done. Run record at: {recorder.path()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
