# mod03 · LangGraph State

## 目标
定义主图在节点间流转的 State TypedDict。子图 State 在 M2 再定义，M1 先用主图 State 跑通。

## 产出
- `src/state.py`

## 与前后模块串联
- 上游：mod02（引用 CandidateRecord）
- 下游：mod05/06/07（节点函数签名 `def f(state: MinerState) -> dict`）、mod08（把节点挂到图上）

## 接口

```python
# src/state.py
from __future__ import annotations
from typing import TypedDict, Annotated
from operator import add
from datetime import datetime
from .models import MaterialMeta, CandidateRecord

class MinerState(TypedDict, total=False):
    # 输入
    material_path: str
    run_id: str

    # Ingest
    material: MaterialMeta
    material_text: str

    # Extract
    candidates: list[CandidateRecord]
    extract_raw: str

    # Coarse
    coarse_done: bool

    # 错误收集
    errors: Annotated[list[str], add]
    started_at: datetime
    finished_at: datetime
```

## 实现要点
- `total=False`：所有字段可选，节点只返回自己写的增量；
- `errors` 用 `Annotated[list, add]`，多个节点 append 不会覆盖；
- M1 阶段还没有子图扇出，所以不需要 `finished_candidates` 字段；等 M2 加子图时再补。

## 验收标准
1. 能 `MinerState(material_path="x.pdf")` 构造；
2. 节点函数返回 `{"candidates": [...]}` 能正确合并到 State。

## 进度
⬜ 未开始
