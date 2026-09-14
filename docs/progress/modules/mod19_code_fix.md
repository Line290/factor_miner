# mod19 · CodeFix 节点

## 目标
根据 CodeExec 的报错 traceback，让 LLM 修改因子代码。

## 产出
- `src/nodes/code_fix.py`
- `src/prompts/code_fix_system.txt`

## 与前后模块串联
- 上游：CodeExec（失败）
- 下游：回到 CodeExec（回边）

## 接口

```python
def code_fix_node(state: dict, *, cfg: AppConfig, llm: LLMClient,
                   data_schema: DataSchema) -> dict:
    """读 code_last_error → LLM 改代码 → 返回更新后的 candidate"""
```

## 实现要点

### Prompt
- System：同 GenerateFactor 的 PIT 规范 + "只输出修复后的完整代码"
- User：
  - 原代码
  - 完整 traceback
  - 可用字段清单
  - 上次修复尝试（避免重复犯同样错误）

### 输出
LLM 返回 JSON：
```json
{"python_code": "def compute(df): ...", "required_fields": [...]}
```

### 防重复
如果连续 2 次报同一种错（如 KeyError），在 prompt 里提示"你可能在用不存在的字段，请核对数据字典"。

## 验收标准
1. KeyError → LLM 改成已存在字段；
2. 语法错误 → LLM 修括号/缩进；
3. 10 轮后仍失败 → 标记 code_fix_failed。

## 进度
⬜ 未开始
