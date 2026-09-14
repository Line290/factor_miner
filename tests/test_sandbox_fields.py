"""一次性验证脚本: required_fields 含非法列时沙箱不应崩溃。

用法: python tests/test_sandbox_fields.py
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd

from src.tools.code_sandbox import run_factor_code

FACTOR_CALC_PYTHON = str(Path("~/miniconda3/envs/factor-calc/bin/python").expanduser())


def make_fixture(tmp: Path) -> Path:
    df = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=30).repeat(2),
            "code": ["A", "B"] * 30,
            "close": range(60),
            "close_adj": [x * 1.0 for x in range(60)],
        }
    )
    p = tmp / "market.parquet"
    df.to_parquet(p)
    return p


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = make_fixture(tmp)

        # 模拟 checkpoint 中被污染的 required_fields（c05 真实案例）:
        # AST 扫描把 df.index / df.reset_index() 当成了数据字段
        poisoned_fields = ["close_adj", "index", "reset_index", "code", "date"]
        code = """
def compute(df):
    return df.groupby("code")["close_adj"].pct_change()
"""

        result = run_factor_code(
            code=code,
            required_fields=poisoned_fields,
            data_dir=data_dir.parent,
            output_path=tmp / "out" / "values.parquet",
            python_bin=FACTOR_CALC_PYTHON,
            timeout_sec=60,
        )

        assert result.success, (
            "沙箱不应因 required_fields 含非列名而失败，"
            f"实际报错:\n{result.error}"
        )
        assert result.values_path is not None
        out = pd.read_parquet(result.values_path)
        assert len(out) == 60, f"输出行数异常: {len(out)}"
        print("PASS: 被污染的 required_fields 不再导致 read_parquet 崩溃")

        # compute 真正用到缺失列 vwap 时仍应失败，且报错可读（含字段名）
        code_needs_vwap = """
def compute(df):
    return df["close_adj"] / df["vwap"]
"""
        result2 = run_factor_code(
            code=code_needs_vwap,
            required_fields=["close_adj", "vwap"],
            data_dir=data_dir.parent,
            output_path=tmp / "out2" / "values.parquet",
            python_bin=FACTOR_CALC_PYTHON,
            timeout_sec=60,
        )
        assert not result2.success, "缺少 compute 实际需要的列时应当失败"
        assert "vwap" in (result2.error or ""), (
            f"报错应包含缺失字段名 vwap，实际:\n{result2.error}"
        )
        print("PASS: 真实缺列仍报错，且错误信息包含字段名")

        # required_fields 漏掉 code/date，但代码用了 df['code'] → 面板索引列应恒定加载
        result3 = run_factor_code(
            code=code,
            required_fields=["close_adj"],
            data_dir=data_dir.parent,
            output_path=tmp / "out3" / "values.parquet",
            python_bin=FACTOR_CALC_PYTHON,
            timeout_sec=60,
        )
        assert result3.success, (
            "date/code 是面板索引列，应恒定加载，"
            f"实际报错:\n{result3.error}"
        )
        print("PASS: 漏列 code/date 时面板索引列仍恒定加载")

        # market.parquet 带索引元数据: date/code 读取时进 MultiIndex,
        # 沙箱应转为普通列交给代码,输出再恢复面板索引
        mi = pd.DataFrame(
            {
                "close_adj": range(60),
            },
            index=pd.MultiIndex.from_product(
                [pd.date_range("2024-01-01", periods=30), ["A", "B"]],
                names=["date", "code"],
            ),
        )
        # 沙箱固定读取 data_dir/market.parquet，MultiIndex fixture 须写到该文件名
        tmp_mi = tmp / "mi_panel"
        tmp_mi.mkdir()
        mi.to_parquet(tmp_mi / "market.parquet")
        result4 = run_factor_code(
            code=code,
            required_fields=["close_adj", "reset_index"],  # 含垃圾字段、漏 code
            data_dir=tmp_mi,
            output_path=tmp / "out4" / "values.parquet",
            python_bin=FACTOR_CALC_PYTHON,
            timeout_sec=60,
        )
        assert result4.success, f"MultiIndex 面板应可用 df['code'] 列式访问，实际报错:\n{result4.error}"
        out4 = pd.read_parquet(result4.values_path)
        assert list(out4.index.names) == ["date", "code"], (
            f"输出应恢复 (date, code) 面板索引，实际: {list(out4.index.names)}"
        )
        print("PASS: MultiIndex 面板转列式访问,输出恢复 (date, code) 索引")

        # 聚合返回(长度不齐)应报错且信息可读
        result5 = run_factor_code(
            code="def compute(df):\n    return df.groupby(\"code\")[\"close_adj\"].mean()",
            required_fields=["close_adj"],
            data_dir=tmp,
            output_path=tmp / "out5" / "values.parquet",
            python_bin=FACTOR_CALC_PYTHON,
            timeout_sec=60,
        )
        assert not result5.success, "聚合返回不逐行对齐,应失败"
        assert "逐行对齐" in (result5.error or ""), f"报错应说明对齐要求:\n{result5.error}"
        print("PASS: 聚合返回被拒绝,报错说明对齐要求")


if __name__ == "__main__":
    main()
