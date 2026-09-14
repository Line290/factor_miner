"""Checkpoint serde 兜底: numpy 标量/数组转 Python 原生类型。

pandas 运算返回 numpy 标量(np.float64/np.bool_),节点若未显式 cast 就写进
state,langgraph 的 msgpack checkpoint 编码会直接 TypeError,且发生在整个
超级步完成后、代价极大。此序列化器在编码失败时做一次深转换兜底。
"""
from __future__ import annotations

import numpy as np
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer


def _to_plain(obj):
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, dict):
        return {k: _to_plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return type(obj)(_to_plain(v) for v in obj)
    return obj


class NumpySafeSerializer(JsonPlusSerializer):
    """常规路径零开销；msgpack 编码遇 numpy 类型时深转换后重试。"""

    def dumps_typed(self, obj):
        try:
            return super().dumps_typed(obj)
        except TypeError:
            return super().dumps_typed(_to_plain(obj))
