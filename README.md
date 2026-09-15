# Factor Miner Agent

基于 **LangGraph 手写 StateGraph ReAct 循环**的单因子挖掘智能体，类 Claude Code 的长程会话：模型自主决定调用哪些工具、调几次、何时停止，支持断点恢复与长上下文压缩。

输入研报/论文/路演纪要，智能体自主完成「理解材料 → 查询数据字典/因子库/业务规则 → 生成因子计算代码 → 沙箱执行 → 回测评估 → 入库」全链路。

## Agentic 会话（Claude Code 式）

```
user --task "从研报提炼 2 个因子"
   ↓
┌─ ReAct 循环 ──────────────────────────────────────────┐
│  agent  (LLM 输出 tool_calls / 最终答案)              │
│    │   ← 无 tool_calls → finalize                     │
│    ↓                                                   │
│  tools  (7 个领域工具：read/query/run/backtest/save)   │
│    │   ← 超 token 预算 → compress（LLM 摘要替换）     │
│    └──────────────────→ agent（继续循环，≤30 轮）     │
└────────────────────────────────────────────────────────┘
   ↓
finalize → 会话元数据（SessionStore）+ SQLite checkpointer
```

- **自主多轮工具调用**：模型自己决定调用序列与终止时机（`agent → tools → agent` 条件路由）
- **完整消息栈**：user/assistant(tool_calls)/tool 消息与 OpenAI Chat Completions 格式一一对应，`tool_call_id` 严格匹配
- **断点恢复**：`--resume <thread_id>` 从 checkpointer 恢复消息快照继续会话
- **长上下文压缩**：消息栈 token 超预算（窗口 × 60%）时，中间轮次压缩为 `[历史会话摘要]`，保留最近 2~3 轮细节
- **安全保护**：最大 30 轮强制收尾、单条工具输出 8K 截断、token 预算告警、`human_in_the_loop` 配置开关（默认全自动）

## 领域工具（首批 7 个）

| 工具 | 作用 | 对应旧流水线节点 |
|------|------|------------------|
| `read_material` | 按页读取材料 | ingest / extract |
| `query_data_schema` | 数据字典（25 字段） | coarse_judge |
| `query_factor_library` | 因子库检索（24 因子） | coarse_judge / fine_filter |
| `query_business_rules` | 业务规则（PIT 等） | coarse_judge |
| `run_factor_code` | 因子代码沙箱执行（factor-calc 环境） | code_exec / code_fix |
| `run_backtest` | IC/IR 回测 | backtest |
| `save_factor` | 达标因子入库 | auto_archive |

> 旧确定性流水线 DAG（ingest → extract → coarse → per-candidate subgraph → backtest → save）已在 MA9 退役，节点逻辑全部迁移为上述工具。`main` 分支保留旧实现可回退。

## 快速开始

```bash
# 1. conda 环境（主环境 + 因子沙箱）
conda create -n factor-miner-agent python=3.11 -y
conda activate factor-miner-agent
pip install -e .

conda create -n factor-calc python=3.11 -y
conda activate factor-calc
pip install pandas numpy pyarrow

# 2. 配置环境变量
export DASHSCOPE_API_KEY=your_key

# 3. 生成数据（或接入真实数据）
python scripts/gen_mock_data.py
python scripts/build_library_factors.py

# 4. 新会话：从研报挖掘因子
python -m src.main --task "阅读材料，提炼 2 个可量化因子并回测入库" \
    --material data/raw/reports/your_report.pdf

# 5. 恢复会话 / 列出会话
python -m src.main --resume <thread_id>
python -m src.main --list-sessions
```

## 配置

所有参数在 [`configs/default.yaml`](configs/default.yaml)：

| 模块 | 说明 |
|------|------|
| `llm` | OpenAI 兼容接口（qwen3.7-flash，DashScope MaaS 端点） |
| `agent` | 会话控制：`max_agent_rounds=30`、`tool_output_truncate_chars=8000`、`messages_max_tokens_ratio=0.6`、`context_window_tokens=131072`、`human_in_the_loop=false` |
| `persistence` | run 目录、checkpointer、`session_store_path`（会话元数据） |
| `robustness` | 并发数、JSON 修复 |

## 目录结构

```
factor_miner/
├── configs/           # YAML 配置（含 agent 会话段）
├── data/               # 数据（gitignore）
│   ├── parquet/        # 行情数据
│   ├── library_factors/  # 因子库值
│   ├── runs/           # 运行留档
│   ├── sessions.json   # 会话元数据（Agentic）
│   └── checkpoints.sqlite  # LangGraph 检查点
├── docs/               # 技术文档 + 改造规划 + 进度看板
├── scripts/            # 数据生成 & 冒烟脚本
├── src/
│   ├── agent_graph.py  # ReAct 主循环图（agent/tools/compress/finalize）
│   ├── agent_tools/    # 领域工具注册表（7 工具 + dispatch）
│   ├── agent_state.py  # 会话状态 + 消息工具函数
│   ├── session_store.py # 会话元数据存储
│   ├── llm.py          # LLMClient（chat_message/chat_stream/chat_messages）
│   └── ...
└── tests/              # 45+ pytest 用例
```

## 测试

```bash
~/miniconda3/envs/factor-miner-agent/bin/python -m pytest tests/ -v
```

## 技术文档

- [Agentic 会话改造规划（决策 + 排期）](docs/agentic_session_refactor_plan.md)
- [技术设计文档](docs/single_factor_miner_agent_design.md)
- [开发进度看板](docs/progress/README.md)

## License

Private project.
