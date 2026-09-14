# mod23 Backtest API 接口（占位）

## 职责
远程回测接口，后续按真实协议实现。

## 配置
```yaml
backtest:
  mode: api
  api:
    mode: async          # sync | async
    endpoint_submit: "http://..."
    endpoint_query: "http://..."
    poll_interval_sec: 5
    timeout_sec: 600
```

## 当前状态
- 接口未实现，`mode: api` 时记录 warning 并跳过回测；
- 后续协议确定后补 `tools/backtest_api.py`。

## 与前后模块串联
- 同 mod22

## 进度
⬜ 未开始
