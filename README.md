# Factor Miner Agent

基于 LangGraph 的单因子挖掘智能体：输入研报/论文/路演纪要，自动抽取候选因子、代码化、沙箱执行、回测评估，输出有效因子。

## 工作流程

```
研报/论文 (PDF/JSON)
       ↓
  Ingest (解析文本+分页)
       ↓
  ExtractCandidates (LLM 切分 N 个候选因子)
       ↓
  CoarseJudge (LLM 粗筛：逻辑/可量化/新颖性)
       ↓
  ┌─ Per-Candidate Subgraph (并行扇出) ─────────┐
  │  FineFilter (novelty / data_avail / business) │
  │       ↓                                       │
  │  Iterate (LLM 根据反馈重写因子描述)            │
  │       ↓                                       │
  │  GenerateFactor (LLM 生成 Python 计算代码)     │
  │       ↓                                       │
  │  CodeExec (subprocess 沙箱执行)                │
  │       ↓ 失败                                  │
  │  CodeFix (多轮对话修复，最多 10 轮)            │
  │       ↓ 成功                                  │
  │  RelevanceCheck (与因子库截面 spearman)        │
  │       ↓                                       │
  │  Backtest (IC/IR 计算)                        │
  │       ↓                                       │
  │  AutoArchive (IC>0.03 且 IR>0.3 自动入库)     │
  └────────────────────────────────────────────────┘
       ↓
  RunRecord (JSON 落盘 + summary)
```

## 架构特点

- **双 conda 环境**：主环境跑 Agent 逻辑，沙箱环境（`factor-calc`）隔离执行因子代码
- **LangGraph 编排**：主图 + Per-Candidate 子图 Send 扇出并行，条件路由控制循环
- **CodeFix 多轮对话**：标准 user/assistant 消息结构，完整迭代历史
- **断点续跑**：SQLite checkpointer，`--resume <run_id>` 从中断处继续
- **PIT 静态检查**：AST 扫描 `shift(-N)`、`rolling(center=True)` 未来函数
- **全自动**：从研报到因子值 + IC/IR 一键跑完，无需人工干预

## 快速开始

```bash
# 1. 创建 conda 环境
conda create -n factor-miner-agent python=3.11 -y
conda activate factor-miner-agent
pip install -e .

conda create -n factor-calc python=3.11 -y
conda activate factor-calc
pip install pandas numpy pyarrow

# 2. 配置环境变量
export DASHSCOPE_API_KEY=your_key

# 3. 生成 mock 数据（或接入真实数据）
python scripts/gen_mock_data.py
python scripts/build_library_factors.py

# 4. 跑一篇研报
python -m src.main --material data/raw/reports/your_report.pdf

# 5. 断点续跑
python -m src.main --resume <run_id>
```

## 配置

所有参数在 [`configs/default.yaml`](configs/default.yaml)：

| 模块 | 说明 |
|------|------|
| `llm` | OpenAI 兼容接口，支持按节点覆盖模型 |
| `fine_filter` | 三道关开关 + 最大迭代轮数 |
| `code_generation` | 沙箱路径、最大修复轮数、PIT 规范 |
| `relevance` | 与因子库相关性阈值 |
| `backtest` | local/api/off 模式，IC/IR 入库阈值 |
| `persistence` | run 目录、checkpointer |
| `robustness` | 并发数、JSON 修复 |

## 目录结构

```
factor_miner/
├── configs/           # YAML 配置
├── data/               # 数据（gitignore）
│   ├── parquet/        # 行情数据
│   ├── library_factors/  # 因子库值
│   └── runs/           # 每次 run 的记录
├── docs/               # 技术文档 + 开发进度
├── scripts/            # 数据生成脚本
├── skills/             # PIT 规范 skill
├── src/
│   ├── nodes/          # LangGraph 节点
│   ├── tools/          # 沙箱/数据字典/因子库/业务规则
│   ├── prompts/        # system prompt 文件
│   └── ...
└── tests/
```

## 技术文档

- [技术设计文档](docs/single_factor_miner_agent_design.md)
- [开发进度看板](docs/progress/README.md)

## License

Private project.
