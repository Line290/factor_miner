from dotenv import load_dotenv
from loguru import logger
import sys

sys.path.insert(0, ".")
load_dotenv()
logger.remove()
logger.add(sys.stderr, level="INFO")

from src.config import load_config
from src.llm import LLMClient
from src.agent_graph import build_agent_graph

cfg = load_config("configs/default.yaml")
llm = LLMClient(cfg.llm)
graph = build_agent_graph(cfg, llm)
out = graph.invoke(
    {"thread_id": "smoke_ma4",
     "task": "查询数据字典中 close_adj 字段是否可用，再查询因子库中是否已有动量相关因子，最后简要总结这两项结果。"},
    config={"configurable": {"thread_id": "smoke_ma4"}},
)
print("\n=== RESULT ===")
print("final_answer:", out.get("final_answer"))
print("agent_rounds:", out.get("agent_rounds"), "| tool_calls:", out.get("tool_calls_count"))
