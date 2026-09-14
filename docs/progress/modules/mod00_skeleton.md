# mod00 · 项目骨架与 CLI

## 目标
搭好可运行的 Python 项目骨架：依赖、目录、CLI 入口，让后续模块能直接往里填代码。

## 产出
- `pyproject.toml`：依赖与构建配置
- `src/__init__.py`、`src/nodes/__init__.py`、`src/tools/__init__.py`、`src/prompts/` 目录
- `src/main.py`：CLI 入口，解析 `--material <path>`、`--config <path>`、`--resume <run_id>`、`--fresh`，调用 graph

## 与前后模块串联
- 上游：无（最底层）
- 下游：所有模块都依赖本模块定义的目录约定（`src/`、`configs/`、`data/`）

## 实现要点

### pyproject.toml 依赖
```toml
[project]
dependencies = [
    "langgraph>=0.2.0",
    "openai>=1.40",
    "pydantic>=2.7",
    "pyyaml>=6.0",
    "pdfplumber>=0.11",
    "pandas>=2.2",
    "pyarrow>=16",
    "loguru>=0.7",
    "tenacity>=8.4",
    "python-dotenv>=1.0",
]
[project.optional-dependencies]
dev = ["pytest", "ruff", "mypy"]
backtest = ["alphalens-reloaded>=0.4"]
```

### CLI 接口
```
python -m src.main --material data/raw/xxx.pdf
                  [--config configs/default.yaml]
                  [--run-id custom_run_id]
                  [--resume <run_id> | --fresh]
```
- `--fresh`：忽略已有 checkpoint，新建 run_id；
- `--resume`：用已有 run_id，从 checkpoint 恢复。

## 验收标准
1. `pip install -e .` 成功；
2. `python -m src.main --help` 打印用法；
3. 空跑 `python -m src.main --material nonexist.pdf` 能报清晰错误；
4. 目录结构与技术文档 §4 一致。

## 进度
⬜ 未开始
