# M6 鲁棒性

## 已完成

### 1. Checkpointer msgpack 类型注册 ✅
- 通过 `JsonPlusSerializer(allowed_msgpack_modules=[...])` 注册

### 2. JSON 修复 ✅
- 装了 `json-repair` 库
- `_parse_json` 三级容错：直接解析 → 找 `{...}` 块 → json_repair 兜底

### 3. PIT 静态扫描 ✅
- AST 扫描 `shift(-N)` 未来函数，直接报错让 CodeFix 修
- `rolling(center=True)` 未来数据检查
- `rolling`/`expanding` 未按 code 分组检查（跨股票混用数据）

### 4. validate_assignment ✅
- CandidateRecord / MaterialMeta 开了 `validate_assignment=True`
- 非法 status 在赋值处立即报错

## 待做

### 5. 日志持久化
- 每个节点的输入/输出摘要落 logs/
- 当前只在终端打印

### 6. PIT 静态扫描（进阶）
- rolling 窗口右边界检查
- cross-sectional 分母是否用全样本
