# mod04 · LLM 客户端封装

## 目标
封装 OpenAI Chat Completion 协议，提供统一的 `chat()` 和 `chat_json()` 接口，处理重试、JSON 解析、模型覆盖。

## 产出
- `src/llm.py`

## 与前后模块串联
- 上游：mod01（读 LLMConfig）
- 下游：mod06（Extract）、mod07（Coarse）、M2/M3 所有需要 LLM 的节点

## 接口

```python
# src/llm.py
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential
import json

class LLMClient:
    def __init__(self, cfg: LLMConfig):
        self.cfg = cfg
        self.client = OpenAI(base_url=cfg.base_url,
                             api_key=os.environ[cfg.api_key_env])

    def chat(self,
             system: str,
             user: str,
             *,
             model_override: str | None = None,
             temperature: float | None = None,
             json_mode: bool = False) -> str:
        """返回模型输出文本。自动应用 tenacity 重试。"""

    def chat_json(self, system: str, user: str,
                  *, model_override: str | None = None) -> dict:
        """chat() + 严格 JSON 解析；失败时尝试 json_repair（如配置开启）。"""
```

## 实现要点
- `chat_json` 调用时传 `response_format={"type": "json_object"}`（OpenAI 兼容协议都支持）；
- JSON 解析失败：
  1. 先用正则抠出第一个 `{...}` 块；
  2. 再尝试 `json_repair`（如配置开启）；
  3. 仍失败则按 `robustness.llm_retry` 重试一次，prompt 末尾追加"上次输出不是合法 JSON，请只输出 JSON"；
- `model_override`：节点传 `"generate_factor"` 时查 `cfg.llm.overrides[node_name]["model"]`；
- loguru 记录每次调用的 token 用量和耗时（不记 prompt 全文，避免日志过大）。

## 验收标准
1. mock OpenAI 接口后，`chat()` 返回字符串；
2. 模型故意返回带 ```json fence 的文本，`chat_json()` 能正确解析；
3. 模型返回非法 JSON，触发重试逻辑（mock 两次失败第三次成功）。

## 进度
⬜ 未开始
