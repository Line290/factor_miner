# mod05 · Ingest 节点

## 目标
把输入材料（PDF / JSON）读成纯文本 + MaterialMeta，供下游 Extract 使用。

## 产出
- `src/nodes/ingest.py`

## 与前后模块串联
- 上游：mod03（读 `material_path`）
- 下游：mod06（读 `material_text`、`material`）

## 接口

```python
# src/nodes/ingest.py
def ingest_node(state: MinerState) -> dict:
    """读材料 → 返回 {material, material_text, run_id, started_at}"""
```

## 实现要点

### PDF 解析
```python
import pdfplumber
def parse_pdf(path: str) -> tuple[str, int]:
    pages_text = []
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            txt = page.extract_text() or ""
            # 用页码标记包裹，下游 Extract 可定位 source_page
            pages_text.append(f"<<<PAGE {i}>>>\n{txt}")
    return "\n\n".join(pages_text), len(pdf.pages)
```

### 路演 JSON 展平
```python
def flatten_roadshow_json(path: str) -> str:
    data = json.loads(Path(path).read_text())
    # 把常见结构（{"speaker":..., "content":...} / {"qa": [...]}）展平成纯文本
    lines = []
    for item in data.get("segments", data if isinstance(data, list) else []):
        if isinstance(item, dict):
            speaker = item.get("speaker", item.get("role", ""))
            content = item.get("content", item.get("text", ""))
            lines.append(f"[{speaker}] {content}")
        else:
            lines.append(str(item))
    return "\n".join(lines)
```

### run_id 生成
```python
from datetime import datetime
def gen_run_id(path: str) -> str:
    stem = Path(path).stem.replace(" ", "_")[:40]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{ts}__{stem}"
```

## 验收标准
1. 给一个真实 PDF，能抽出文本并保留 `<<<PAGE n>>>` 标记；
2. 给一个路演 JSON，能展平成对话文本；
3. 文件不存在/加密 PDF 时，抛出带清晰原因的异常；
4. `run_id` 唯一且可读。

## 进度
⬜ 未开始
