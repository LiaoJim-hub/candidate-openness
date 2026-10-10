# adapters · 采集适配器（BYO）

本目录**只定义形状，不提供取数**。仓库不内置抓取、不绕过反爬、不提供真实数据。

- `example_adapter.py`：契约骨架。`fetch_candidates()` 抛 `NotImplementedError`，
  强迫你用自己的合规方式实现；另含 `classify()` / `to_measure_payload()` 两个纯函数，
  把你的原始记录转成 `measure.py` 能吃的 payload。
- 你的适配器**不要**提交进本仓库（含真实入口名/真实数据的），放在本地或私有分支。

## payload 契约（measure.py 的输入）

```json
{
  "taken_at": "2026-10-10T00:00:00Z",
  "independence": "none",
  "entries": [
    {
      "entry": "入口标识",
      "intent": "通勤鞋",
      "items": [
        {"relation": "independent", "rank": 1, "id": "c1", "evidence": []},
        {"relation": "marked_paid", "rank": 2, "id": "c2", "evidence": []}
      ]
    }
  ]
}
```

`relation` 必须取 PROTOCOL §3 词表中的 7 个值之一；不在词表内的值会被判为 `unknown`
并保守计入"非开放"，同时出现在告警里。

## 禁止提交的内容

- 绕过验证码、登录限制、频率限制的代码；
- 抓取个人信息、评论、订单、位置数据的代码；
- 未经授权的真实平台数据集；
- 用于攻击、敲诈、做空、商业诋毁的用途。
