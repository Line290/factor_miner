# mod16 · GenerateFactor 节点

## 目标
把通过细筛的候选因子转成正式的 `formula_latex + python_code + required_fields`。

## 产出
- `src/nodes/generate_factor.py`
- `src/prompts/generate_factor_system.txt`

## 与前后模块串联
- 上游：FineFilter（`candidate.fine_passed == True`）
- 下游：CodeExec 节点

## 接口

```python
def generate_factor_node(state: dict, *,
                          cfg: AppConfig, llm: LLMClient,
                          data_schema: DataSchema) -> dict:
    """读 candidate → LLM 生成代码 → 返回 {candidate}"""
```

## 实现要点

### Prompt 结构
1. **System**：
   - 角色：量化因子代码工程师
   - 注入 `skills/factor-calc/references/rules-zh.md` 全文（PIT 规范）
   - 代码签名约束：`def compute(df: pd.DataFrame) -> pd.Series`
   - 输入 df 索引 `(date, code)` MultiIndex，列是可用字段
   - 不允许联网/读文件/调外部 API
   - 先 winsorize 再 zscore
   - T 日信号 T+1 成交
2. **User**：候选的 name/motivation/logic_desc/formula_draft + 数据字典摘要

### 输出解析
LLM 返回 JSON：
```json
{
  "formula_latex": "ICM = ...",
  "python_code": "def compute(df): ...",
  "required_fields": ["close_adj", ...]
}
```

### AST 二次校验
代码生成后，用 `ast` 扫描 `df["xxx"]` 和 `df.xxx`，补充 LLM 漏列的字段。

## 验收标准
1. 输出代码能被 `ast.parse` 解析；
2. 代码包含 `def compute(df: pd.DataFrame) -> pd.Series:`；
3. required_fields 与代码中实际用到的字段一致；
4. formula_latex 是合法 LaTeX。

## 进度
⬜ 未开始
