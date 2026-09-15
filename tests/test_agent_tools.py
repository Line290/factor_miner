"""MA3: 工具注册表测试（schema 校验、dispatch 异常包装、工具行为）。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agent_tools import ToolContext, dispatch, tool_schemas
from src.config import load_config
from src.tools.business_rule import BusinessRules
from src.tools.data_schema import DataSchema
from src.tools.factor_library import FactorLibrary


@pytest.fixture(scope="module")
def ctx(tmp_path_factory):
    cfg = load_config("configs/default.yaml")
    data_schema_path = cfg.fine_filter.data_availability.data_schema_path
    fl = FactorLibrary(data_schema_path.parent / "factor_library_index.yaml")
    ds = DataSchema(data_schema_path)
    br = BusinessRules(cfg.fine_filter.business_rules.rules_path)
    run_dir = tmp_path_factory.mktemp("run")
    return ToolContext(
        cfg=cfg,
        thread_id="test_thread",
        run_dir=run_dir,
        data_dir=Path(cfg.persistence.run_root).parent / "parquet",
        recorder=None,
        material_text=(
            "<<<PAGE 1>>>\n动量因子：过去20日收益率。\n"
            "<<<PAGE 2>>>\n代码示例：df['close_adj'].pct_change(20)。"
        ),
        factor_library=fl,
        data_schema=ds,
        business_rules=br,
    )


def test_tool_schemas_well_formed():
    schemas = tool_schemas()
    names = [s["function"]["name"] for s in schemas]
    assert len(names) == len(set(names)) == 7
    for s in schemas:
        assert s["function"]["description"]
        assert s["function"]["parameters"]["type"] == "object"
        assert isinstance(s["function"]["parameters"].get("properties", {}), dict)


def test_dispatch_unknown_tool(ctx):
    out = json.loads(dispatch("no_such_tool", {}, ctx))
    assert "error" in out


def test_dispatch_wraps_exception(ctx):
    # query_factor_library 的 keywords 传非字符串 → AttributeError，应被包装为 error
    out = json.loads(dispatch("query_factor_library", {"keywords": 123}, ctx))
    assert "error" in out
    assert "AttributeError" in out["error"]


def test_read_material_toc(ctx):
    out = json.loads(dispatch("read_material", {}, ctx))
    assert out["total_pages"] == 2
    assert "[p1]" in out["目录"]
    assert "[p2]" in out["目录"]


def test_read_material_single_page(ctx):
    out = json.loads(dispatch("read_material", {"page": 2}, ctx))
    assert out["page"] == 2
    assert "pct_change" in out["text"]


def test_read_material_page_not_found(ctx):
    out = json.loads(dispatch("read_material", {"page": 9}, ctx))
    assert "error" in out


def test_query_data_schema_summary(ctx):
    out = json.loads(dispatch("query_data_schema", {}, ctx))
    assert "可用字段" in out["summary"]
    assert "date" in out["summary"]


def test_query_data_schema_fields(ctx):
    out = json.loads(dispatch("query_data_schema", {"fields": ["close_adj", "not_a_field"]}, ctx))
    assert "close_adj" in out["known_fields"]
    assert "not_a_field" in out["unknown_fields"]
    assert out["all_available"] is False


def test_query_factor_library_keywords(ctx):
    out = json.loads(dispatch("query_factor_library", {"keywords": "动量"}, ctx))
    # 因子库可能没有"动量"关键词；只断言结构正确
    assert "count" in out
    if out["count"] > 0:
        assert "factors" in out


def test_query_business_rules(ctx):
    out = json.loads(dispatch("query_business_rules", {}, ctx))
    assert isinstance(out["rules"], str)


def test_dispatch_truncation(ctx):
    # 小截断阈值验证输出被截断
    big_material = "<<<PAGE 1>>>\n" + "A" * 5000
    ctx2 = ToolContext(
        cfg=ctx.cfg, thread_id="t2", run_dir=ctx.run_dir,
        data_dir=ctx.data_dir, recorder=None, material_text=big_material,
        factor_library=ctx.factor_library, data_schema=ctx.data_schema,
        business_rules=ctx.business_rules,
    )
    out = dispatch("read_material", {"page": 1}, ctx2, truncate_chars=500)
    assert len(out) <= 500
    assert "已截断" in out
