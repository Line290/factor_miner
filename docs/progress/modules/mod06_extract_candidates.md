# mod06 · ExtractCandidates 节点

## 目标
LLM 从材料文本中切分 N 个候选因子，每个候选含 name / motivation / logic_desc / formula_draft / source_page / source_excerpt。

## 产出
- `src/nodes/extract_candidates.py`
- `src/prompts/extract_candidates.j2`（Jinja2 模板，M1 阶段可直接用 Python f-string，但留模板位置）

## 与前后模块串联
- 上游：mod04（LLMClient）、mod05（material_text）
- 下游：mod07（CoarseJudge 读 candidates）

## 接口

```python
# src/nodes/extract_candidates.py
def extract_candidates_node(state: MinerState, *,
                            cfg: AppConfig,
                            llm: LLMClient) -> dict:
    """切片 → 逐片抽 → 合并去重 → 返回 {candidates, extract_raw}"""
```

## 实现要点

### 切片
材料可能很长，按 `<<<PAGE n>>>` 切，每片 ≤ 6000 字符；超长页再按段落二次切。

### Prompt（system）
```
你是量化因子挖掘专家。从给定文本中抽取所有"可被量化计算的选股因子"。
要求：
1. 每个因子给出 name（简短标识）、motivation（为什么可能有效）、
   logic_desc（变量间关系）、formula_draft（公式雏形）。
2. 只抽可计算因子，不抽纯观点。
3. source_excerpt 必须是原文 ≤500 字片段，source_page 是该片段所在页码。
4. 输出 JSON：{"candidates": [{"name":..., "motivation":..., "logic_desc":...,
   "formula_draft":..., "source_page":int, "source_excerpt":...}, ...]}
5. 不要输出多余解释。
```

### 合并与去重
```python
def dedup(cands: list[dict]) -> list[dict]:
    # 按 name 小写 + logic_desc 前 50 字哈希去重
    seen = set()
    out = []
    for c in cands:
        key = (c["name"].strip().lower(), c["logic_desc"][:50])
        if key in seen: continue
        seen.add(key); out.append(c)
    return out[:cfg.extraction.max_candidates_per_doc]
```

### candidate_id 规则
`f"{run_id}_c{idx:02d}"`，idx 从 1 开始。

## 验收标准
1. 给一段含 2-3 个因子的模拟文本，LLM 能抽出对应数量的候选；
2. 每个候选的 5 个必填字段都非空；
3. `source_page` 是整数；
4. 总数不超过 `max_candidates_per_doc`；
5. LLM 输出 JSON 损坏时能走到 retry 逻辑。

## 进度
⬜ 未开始
