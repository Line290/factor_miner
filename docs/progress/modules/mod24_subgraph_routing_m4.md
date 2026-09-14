# mod24 子图路由改造

## 改动
子图节点顺序从：
```
fine_filter → iterate ↻ → generate_factor → code_exec → code_fix ↻ → save
```
改成：
```
fine_filter → iterate ↻ → generate_factor → code_exec → code_fix ↻
  → relevance_check → backtest → save
```

## 路由函数
```python
def route_after_relevance(state):
    c = state["candidate"]
    if c.corr_passed:
        return "backtest"
    return "save"   # status=high_correlation

def route_after_code_exec(state):
    if c.code_runnable:
        return "relevance_check"
    if c.code_fix_rounds >= max:
        return "save"
    return "code_fix"
```

## 进度
⬜ 未开始
