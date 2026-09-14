"""Code sandbox: execute factor code in the factor-calc conda env."""
from __future__ import annotations

import ast
import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SandboxResult:
    success: bool
    values_path: str | None = None
    error: str | None = None
    stdout: str = ""


_FORBIDDEN_CALLS = {"read_parquet", "read_csv", "read_excel", "open", "read_json"}


def _validate_code(code: str) -> str | None:
    """AST scan: reject imports, file reads, PIT violations, top-level statements."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return f"SyntaxError: {e}"

    # Build parent map for ancestor checks
    parent: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parent[child] = node

    def _has_groupby_ancestor(node: ast.Call) -> bool:
        """Check if this rolling/expanding call is on a groupby result."""
        # The call chain is: df.groupby('code')['close_adj'].rolling(N)
        # node.func is Attribute('rolling'), node.func.value is the subscript/attr chain
        # Walk down from node.func.value to find groupby call
        cur: ast.AST | None = node.func
        depth = 0
        while cur is not None and depth < 10:
            if isinstance(cur, ast.Call):
                f = cur.func
                if isinstance(f, ast.Attribute) and f.attr == "groupby":
                    return True
            # Go deeper into the value/obj chain
            if isinstance(cur, ast.Attribute):
                cur = cur.value
            elif isinstance(cur, ast.Subscript):
                cur = cur.value
            elif isinstance(cur, ast.Call):
                # e.g. df.groupby(...) — already checked above; go to func
                cur = cur.func
            else:
                break
            depth += 1
        return False

    for node in ast.walk(tree):
        # No imports
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            return "禁止 import 语句。pandas/numpy 已提供，直接用 pd/np。"
        # No file reads
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in _FORBIDDEN_CALLS:
                return f"禁止 {func.attr}：df 已由沙箱传入，不要读文件。"
            if isinstance(func, ast.Name) and func.id in _FORBIDDEN_CALLS:
                return f"禁止 {func.id}：df 已由沙箱传入，不要读文件。"
            # PIT: no shift(-N) — look-ahead bias
            if isinstance(func, ast.Attribute) and func.attr == "shift":
                if node.args and isinstance(node.args[0], ast.UnaryOp) and isinstance(node.args[0].operand, ast.Constant):
                    n = node.args[0].operand.value
                    if n and n > 0:
                        return f"PIT 违规: shift(-{n}) 使用了未来数据。信号 T 日、T+1 成交，只能用 shift(正数) 或不用 shift。"
            # PIT: rolling(center=True) uses future data
            if isinstance(func, ast.Attribute) and func.attr == "rolling":
                for kw in node.keywords:
                    if kw.arg == "center" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                        return "PIT 违规: rolling(center=True) 使用了未来数据。pandas rolling 默认右对齐（右边界=当前行），不要设 center=True。"
            # PIT: expanding/rolling without groupby on panel data
            if isinstance(func, ast.Attribute) and func.attr in ("rolling", "expanding"):
                if not _has_groupby_ancestor(node):
                    return f"PIT 提醒: .{func.attr}() 未按 code 分组。时间序列窗口必须 groupby('code') 后再 {func.attr}，否则会跨股票混用数据。"
        # No top-level assignments/expressions outside function def
        if isinstance(node, ast.Assign) and getattr(node, "col_offset", 0) == 0:
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "df":
                    return "禁止顶层赋值 df = ...：df 已由沙箱传入，只写 def compute(df): ..."
    return None


def run_factor_code(
    code: str,
    required_fields: list[str],
    data_dir: Path,
    output_path: Path,
    python_bin: str,
    timeout_sec: int = 60,
) -> SandboxResult:
    """Execute factor code in a subprocess."""
    # Pre-execution validation
    validation_error = _validate_code(code)
    if validation_error:
        return SandboxResult(success=False, error=f"代码校验失败: {validation_error}")
    data_dir = Path(data_dir)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Build the wrapper script
    fields_repr = json.dumps(required_fields)
    data_path = str(data_dir / "market.parquet")
    out_path = str(output_path)

    wrapper = f'''
import pandas as pd
import numpy as np
import sys
import traceback

# ---- User code ----
{code}

# ---- Load data ----
try:
    required_fields = {fields_repr}
    # required_fields 由 LLM 生成/补充，可能混入非列名（如 df.index 误扫成字段），
    # 以 parquet 实际 schema 为准过滤，缺列留给 compute() 的 KeyError 去报
    import pyarrow.parquet as _papq
    _schema_cols = set(_papq.read_schema("{data_path}").names)
    _valid = [f for f in required_fields if f in _schema_cols]
    _dropped = sorted(set(required_fields) - set(_valid))
    if _dropped:
        print(f"WARNING: required_fields 不在数据列中，已忽略: {{_dropped}}", file=sys.stderr)
    # 面板索引列恒定加载，保证 df['code']/df['date'] 总是可用，
    # 不依赖 LLM 在 required_fields 里记得列出
    _valid = [f for f in dict.fromkeys(("date", "code") + tuple(_valid))
              if f in _schema_cols]
    df = pd.read_parquet("{data_path}", columns=_valid or None)
    # date/code 转为普通列：LLM 生成的代码普遍用 df['code']/groupby('code') 列式访问；
    # 先保存面板索引，compute 返回后恢复，保证因子输出能按 (date, code) 对齐回测
    _panel_index = df.index
    df = df.reset_index()
    print(f"Loaded df: {{df.shape}}, columns: {{list(df.columns)}}", file=sys.stderr)

    # ---- Run factor ----
    result = compute(df)

    if not isinstance(result, pd.Series):
        raise TypeError(f"compute must return pd.Series, got {{type(result)}}")

    if len(result) != len(df):
        raise ValueError(
            f"compute 返回长度 {{len(result)}} 与 df 行数 {{len(df)}} 不一致，"
            "因子必须逐行对齐面板：组内运算用 groupby(...).transform，不要用聚合")

    if result.dropna().empty:
        raise ValueError(
            "compute 返回全 NaN。检查 groupby/transform 用法、窗口参数、字段是否选对。")

    result.index = _panel_index

    result.name = "factor"
    result.to_frame().to_parquet("{out_path}")
    print("OK")
except Exception:
    traceback.print_exc()
    sys.exit(1)
'''

    with tempfile.TemporaryDirectory() as tmpdir:
        script_path = Path(tmpdir) / "_factor_script.py"
        script_path.write_text(wrapper, encoding="utf-8")

        try:
            proc = subprocess.run(
                [python_bin, str(script_path)],
                cwd=tmpdir,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
            )
        except subprocess.TimeoutExpired:
            return SandboxResult(
                success=False,
                error=f"Execution timed out after {timeout_sec}s",
                stdout="",
            )
        except FileNotFoundError:
            return SandboxResult(
                success=False,
                error=f"Python binary not found: {python_bin}. "
                      f"请确认 factor-calc conda 环境已创建。",
                stdout="",
            )

        if proc.returncode != 0:
            # Truncate error to avoid huge tracebacks
            err = proc.stderr[-3000:] if proc.stderr else "Unknown error"
            return SandboxResult(
                success=False,
                error=err,
                stdout=proc.stdout[-1000:],
            )

        if not output_path.exists():
            return SandboxResult(
                success=False,
                error=f"Script exited 0 but output not found: {output_path}",
                stdout=proc.stdout[-1000:],
            )

        return SandboxResult(
            success=True,
            values_path=str(output_path),
            error=None,
            stdout=proc.stdout[-1000:],
        )
