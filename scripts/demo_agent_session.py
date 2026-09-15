"""Agentic 会话演示脚本：一条命令体验 Claude Code 式 ReAct 循环。

用法:
    python scripts/demo_agent_session.py          # 快速演示（只读查询，约 20~40 秒，qwen 真实调用）
    python scripts/demo_agent_session.py --full   # 完整挖掘演示（因子代码→回测→入库，约 3~5 分钟）

前置：已 export DASHSCOPE_API_KEY（或 .env），conda 环境 factor-miner-agent。
"""
from __future__ import annotations

import argparse
import sys

from dotenv import load_dotenv
from loguru import logger

sys.path.insert(0, ".")
load_dotenv()
logger.remove()
logger.add(sys.stderr, level="WARNING")   # 关掉 INFO 刷屏，只留工具/警告

from src.config import load_config
from src.llm import LLMClient
from src.main import run_agentic_session

QUICK_TASK = (
    "请依次查询并汇报：1) 数据字典中 close_adj 字段是否可用；"
    "2) 因子库中是否已有动量相关因子；3) 业务规则对 PIT（未来函数）的要求。"
    "最后用一句话总结三项结果。"
)

FULL_TASK = (
    "阅读材料，这是一篇因子周报（小市值/反转/动量风格领涨）。请完成单因子挖掘："
    "1) 先查询数据字典与业务规则确认可用字段；"
    "2) 提炼 1 个能用现有行情字段直接计算的候选因子（避开不可用数据）；"
    "3) 用 run_factor_code 计算因子值；"
    "4) 用 run_backtest 回测 IC/IR；"
    "5) 若达标则 save_factor 入库。"
    "最后结构化汇报因子逻辑、代码、回测指标与入库结果。"
)


def main() -> int:
    ap = argparse.ArgumentParser(description="Agentic 会话演示")
    ap.add_argument("--full", action="store_true", help="完整挖掘演示（默认只读快速演示）")
    args = ap.parse_args()

    cfg = load_config("configs/default.yaml")
    llm = LLMClient(cfg.llm)

    if args.full:
        print("== 完整挖掘演示：真实研报 → 自主因子挖掘 → 回测 → 入库 ==")
        out = run_agentic_session(
            cfg, llm,
            task=FULL_TASK,
            material_path="data/raw/reports/report6.pdf",
        )
    else:
        print("== 快速演示：qwen 自主调用领域工具（数据字典 / 因子库 / 业务规则）==")
        print("（下方 ⟳ = 模型决定调用工具，⚙ = 工具执行结果，⏹ = 模型输出）\n")
        out = run_agentic_session(cfg, llm, task=QUICK_TASK)

    print(f"\n[会话 {out['thread_id']} 完成] rounds={out.get('agent_rounds', 0)} "
          f"tools={out.get('tool_calls_count', 0)}")
    print("\n接下来可以试试：")
    print(f"  python -m src.main --list-sessions            # 查看会话列表")
    print(f"  python -m src.main --resume {out['thread_id']}   # 恢复本会话继续对话")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
