# mod17 · CodeSandbox 工具

## 目标
在 `factor-calc` conda 环境中沙箱执行因子代码，返回因子值或报错。

## 产出
- `src/tools/code_sandbox.py`

## 与前后模块串联
- 上游：CodeExec 节点
- 下游：CodeExec 节点拿结果决定下一步

## 接口

```python
# src/tools/code_sandbox.py
@dataclass
class SandboxResult:
    success: bool
    values_path: str | None = None
    error: str | None = None
    stdout: str = ""

def run_factor_code(
    code: str,
    required_fields: list[str],
    data_dir: Path,           # data/parquet/
    output_path: Path,        # 因子值 parquet 输出路径
    python_bin: str,
    timeout_sec: int = 60,
) -> SandboxResult:
    """1. 写临时脚本（包 compute + 读 parquet + 调 compute + 写结果）
       2. subprocess 调 python_bin 执行
       3. 捕获 stdout/stderr/exit_code
       4. 成功校验结果 parquet"""
```

## 实现要点

### 临时脚本结构
```python
# tmp_script.py
import pandas as pd
import sys, json

# 用户代码
{code}

# 读数据（从 parquet 读 required_fields）
df = pd.read_parquet("{data_dir}/market.parquet", columns={required_fields})

# 执行
result = compute(df)

# 校验
assert isinstance(result, pd.Series), "compute must return pd.Series"
result.name = "factor"
result.to_frame().to_parquet("{output_path}")
print("OK")
```

### subprocess 调用
```python
proc = subprocess.run(
    [python_bin, str(script_path)],
    cwd=tmpdir,
    capture_output=True,
    text=True,
    timeout=timeout_sec,
)
```

### 数据加载
M3 阶段先用一个 mock parquet（用户后续替换成真实行情数据）。脚本里从 `data/parquet/market.parquet` 读所有 required_fields。

## 验收标准
1. 简单因子（如 `df["close_adj"].pct_change(20)`）能跑通；
2. 故意写错代码（如 `df["nonexistent"]`）能返回 KeyError；
3. 死循环能超时杀掉；
4. 结果 parquet 索引是 `(date, code)`。

## 进度
⬜ 未开始
