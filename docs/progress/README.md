# 开发进度看板

> 配套技术设计文档：[`../single_factor_miner_agent_design.md`](../single_factor_miner_agent_design.md)
> 状态图例：⬜ 未开始 / 🟡 进行中 / ✅ 完成 / ⏸ 阻塞

## 里程碑总览

| 里程碑 | 范围 | 状态 |
|---|---|---|
| M1 | 主图骨架跑通：Ingest + Extract + CoarseJudge，产出 RunRecord | ✅ |
| M2 | Per-Candidate Subgraph：FineFilter 三关 + Iterate | ✅ |
| M3 | GenerateFactor + CodeExec 沙箱 + CodeFix | ✅ |
| M4 | RelevanceCheck + Backtest 模块化（local/api） | ✅ local 跑通，api 占位 |
| M5 | Checkpointer 断点续跑 | ✅ |
| M6 | 鲁棒性：JSON 修复、PIT 静态扫描、日志 | 🟡 基础版完成 |
| M7 | 业务规则 SKILL 完善、阈值校准、真实数据接入 | ⬜ |

## 模块清单（M1 展开）

| ID | 模块 | 依赖 | 产出文件 | 状态 |
|---|---|---|---|---|
| mod00 | 项目骨架 / CLI / 依赖 | — | `pyproject.toml`, `src/main.py` | 🟡 代码已写，待 pip install |
| mod01 | 配置加载与校验 | mod00 | `src/config.py` | ✅ |
| mod02 | pydantic 数据模型 | mod01 | `src/models.py` | ✅ |
| mod03 | LangGraph State | mod02 | `src/state.py` | ✅ |
| mod04 | LLM 客户端封装 | mod01 | `src/llm.py` | ✅ |
| mod05 | Ingest 节点 | mod01, mod02 | `src/nodes/ingest.py` | ✅ |
| mod06 | ExtractCandidates 节点 | mod02, mod04 | `src/nodes/extract_candidates.py` | ✅ |
| mod07 | CoarseJudge 节点 | mod02, mod04 | `src/nodes/coarse_judge.py` | ✅ |
| mod08 | 主图组装 | mod03, 05-07 | `src/graph.py` | ✅ |
| mod09 | RunRecord 落盘 | mod02 | `src/persistence.py` | ✅ |
| mod10 | PerCandidateState | mod03 | `src/state.py` | ✅ |
| mod11 | 逻辑新颖性检查 | mod10 | `src/tools/factor_library.py` | ✅ |
| mod12 | 数据可得性检查 | mod10 | `src/tools/data_schema.py` | ✅ |
| mod13 | 业务方向检查 | mod10 | `src/tools/business_rule.py` | ✅ |
| mod14 | Iterate 节点 | mod11-13 | `src/nodes/iterate.py` | ✅ |
| mod15 | 子图组装+Send扇出 | mod10-14 | `src/graph.py` | ✅ |
| mod16 | GenerateFactor 节点 | mod15 | `src/nodes/generate_factor.py` | ✅ |
| mod17 | CodeSandbox 工具 | mod16 | `src/tools/code_sandbox.py` | ✅ |
| mod18 | CodeExec 节点 | mod17 | `src/nodes/code_exec.py` | ✅ |
| mod19 | CodeFix 节点 | mod18 | `src/nodes/code_fix.py` | ✅ |
| mod20 | 子图路由改造 | mod16-19 | `src/graph.py` | ✅ |
| mod21 | RelevanceCheck 节点 | mod20 | `src/nodes/relevance_check.py` | ✅ |
| mod22 | Backtest Local 节点 | mod21 | `src/nodes/backtest.py` | ✅ |
| mod23 | Backtest API（占位） | mod22 | — | ⬜ |
| mod24 | M4 子图路由 | mod21-22 | `src/graph.py` | ✅ |

## 模块文档索引

M1 模块设计文档见 [`modules/`](./modules/)：

- [mod00 项目骨架](./modules/mod00_skeleton.md)
- [mod01 配置加载](./modules/mod01_config.md)
- [mod02 数据模型](./modules/mod02_models.md)
- [mod03 LangGraph State](./modules/mod03_state.md)
- [mod04 LLM 客户端](./modules/mod04_llm.md)
- [mod05 Ingest 节点](./modules/mod05_ingest.md)
- [mod06 ExtractCandidates 节点](./modules/mod06_extract_candidates.md)
- [mod07 CoarseJudge 节点](./modules/mod07_coarse_judge.md)
- [mod08 主图组装](./modules/mod08_graph.md)
- [mod09 RunRecord 落盘](./modules/mod09_persistence.md)

M2 模块：

- [mod10 PerCandidateState](./modules/mod10_per_candidate_state.md)
- [mod11 逻辑新颖性检查](./modules/mod11_novelty_check.md)
- [mod12 数据可得性检查](./modules/mod12_data_avail_check.md)
- [mod13 业务方向检查](./modules/mod13_biz_check.md)
- [mod14 Iterate 节点](./modules/mod14_iterate.md)
- [mod15 子图组装](./modules/mod15_subgraph.md)

M3 模块：

- [mod16 GenerateFactor 节点](./modules/mod16_generate_factor.md)
- [mod17 CodeSandbox 工具](./modules/mod17_code_sandbox.md)
- [mod18 CodeExec 节点](./modules/mod18_code_exec.md)
- [mod19 CodeFix 节点](./modules/mod19_code_fix.md)
- [mod20 子图路由改造](./modules/mod20_subgraph_routing.md)

M4 模块：

- [mod21 RelevanceCheck 节点](./modules/mod21_relevance_check.md)
- [mod22 Backtest Local](./modules/mod22_backtest_local.md)
- [mod23 Backtest API（占位）](./modules/mod23_backtest_api.md)
- [mod24 M4 子图路由](./modules/mod24_subgraph_routing_m4.md)

## 进度更新规则

每完成一个模块，把上表状态从 ⬜ 改成 ✅，并在对应模块文档末尾追加"实现记录"小节（提交日期、关键决策、偏离设计文档之处）。

## Agentic 会话改造（feat/claude-code-like-agent）

> 规划文档：[`../agentic_session_refactor_plan.md`](../agentic_session_refactor_plan.md)
> 目标：Claude Code 式长程会话 + 工具调用（ReAct 循环），直接替换流水线 DAG

| ID | 模块 | 范围 | 状态 |
|---|---|---|---|
| MA1 | LLM 客户端扩展 | `chat_message` 返回完整 message（tool_calls 透传）+ `chat_stream` 流式 + qwen 冒烟 | ✅ 2026-09-15 |
| MA2 | 会话状态与消息模型 | `AgentSessionState` + 消息构造/校验/截断 | ✅ 2026-09-15 |
| MA3 | 工具注册表 | 7 个工具 schema + 执行函数适配 | ✅ 2026-09-15 |
| MA4 | ReAct 主循环图 | agent/tools/finalize + 条件路由 + 轮数保护 | ✅ 2026-09-15 |
| MA5 | 会话持久化 | threads 元数据 + `--list-sessions` / `--resume` | ⬜ |
| MA6 | CLI 批处理入口 | `--task`/`--material`/`--resume` + 流式终端 | ⬜ |
| MA7 | 安全保护 | 轮数上限、输出截断、token 预算 | ⬜ |
| MA8 | 上下文压缩 | 摘要生成与替换（基础版） | ⬜ |
| MA9 | 流水线迁移与退役 | 旧节点逻辑迁移 + 对照回归 | ⬜ |
| MA10 | 测试与验收 | 全量测试、文档、演示 | ⬜ |

**MA1/MA2 实现记录（2026-09-15）**：
- `LLMClient` 新增 `chat_message()`（返回 OpenAI 原生 assistant message dict，tool_calls 原样透传）与 `chat_stream()`（流式增量，yield content / tool_calls 分片）；旧 `chat_messages()` 接口保持字符串返回，向后兼容。
- 冒烟测试 `scripts/smoke_tool_calls.py` 真实调用 qwen3.7-flash：第 1 轮返回 `add_numbers` tool_call，工具执行回填后第 2 轮模型给出最终答案 579，tool_call_id 严格匹配。
- 关键决策：消息模型用 OpenAI 原生 dict（非 langchain BaseMessage），零转换成本。
- 单测：`tests/test_llm_tool_calls.py`（5 用例）+ `tests/test_agent_state.py`（10 用例）全绿。

**MA3/MA4 实现记录（2026-09-15）**：
- MA3 `src/agent_tools/registry.py`：7 个工具（read_material / query_data_schema / query_factor_library / query_business_rules / run_factor_code / run_backtest / save_factor），OpenAI tools schema + `dispatch()` 统一异常包装与输出截断。
- MA4 `src/agent_graph.py`：手写 StateGraph ReAct 循环（agent → tools → agent），条件路由 + `max_agent_rounds` 轮数保护 + 复用 `checkpoints.sqlite`（thread_id = 会话）。
- 首轮自动注入 system 提示并整体写回消息栈（会话完整性）。
- 端到端冒烟 `scripts/smoke_agent_session.py` 真实跑通：qwen3.7-flash 自主连续调用 `query_data_schema` + `query_factor_library` 两个工具并给出结构化总结。
- 单测：`tests/test_agent_tools.py`（11 用例）+ `tests/test_agent_graph.py`（4 用例，含循环/轮数保护/checkpointer 恢复）。
