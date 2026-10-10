#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
采集适配器 · 契约骨架（BYO Adapter）

本文件**不联网、不抓取**，只固定"输入输出形状"。
它不回答"怎么抓、能不能抓、抓了合不合规"——那是门外的前提。

你要做的：
  1. 自己实现 fetch_candidates()（用你自己的合规取数方式）；
  2. 用 to_measure_payload() 把你的记录转成 measure.py 能吃下的 payload；
  3. 承担采集、存储、判定、公开的全部合规责任。
"""
from __future__ import annotations
from typing import Any


# ----------------------------------------------------------------------
# 1) 取数：你来实现（本骨架直接抛异常，防止误用）
# ----------------------------------------------------------------------
def fetch_candidates(intent: str, ctx: dict) -> dict:
    """
    返回"入口直接给出的候选集"，顺序保留。

    规则（硬性）：
      - 只取**入口直接给出的首轮候选**；
      - 不把追问、翻页、登录后追加结果混入，除非单独标记；
      - 不在本函数内做任何指标计算。
    """
    raise NotImplementedError(
        "请实现你自己的合规取数方式。本仓库不提供、不内置任何爬虫。"
    )
    # 期望返回（示例形状，勿照搬）：
    # {
    #     "intent_id": intent,
    #     "entry": "某入口",
    #     "captured_at": "2026-10-10T00:00:00Z",
    #     "context": {"region": "...", "device": "...", "login_state": "..."},
    #     "candidates": [
    #         {
    #             "id": "...", "rank": 1, "title": "...", "url": "...",
    #             "is_paid_labeled": False,
    #             "is_affiliated": False,
    #             "is_suspected_paid": False,
    #             "evidence": []
    #         }
    #     ]
    # }


# ----------------------------------------------------------------------
# 2) 归类：把候选的布尔标记映射到 measure.py 的 relation 词表
# ----------------------------------------------------------------------
def classify(cand: dict) -> str:
    """
    映射优先级：标注付费 > 疑似付费 > 关联方 > 中立。
    relation 词表见 PROTOCOL §3：
      marked_paid / suspected_paid / self / affiliate / equity / exclusive / independent
    """
    if cand.get("is_paid_labeled"):
        return "marked_paid"
    if cand.get("is_suspected_paid"):
        return "suspected_paid"
    if cand.get("is_affiliated"):
        # 更细的关联类型（self/affiliate/equity/exclusive）由你的规则给出；
        # 这里保守落到最通用的 affiliate。
        return cand.get("related_kind", "affiliate")
    return "independent"


# ----------------------------------------------------------------------
# 3) 转 payload：把你的记录拼成 measure.py 的输入
# ----------------------------------------------------------------------
def to_measure_payload(records: list[dict],
                       independence: str = "none",
                       taken_at: str | None = None) -> dict[str, Any]:
    """
    records: 一组 fetch_candidates() 的返回值（每个含 entry/intent_id/candidates/...）
    independence: none | has_relation | provided_by_entry  (见 PROTOCOL §6)
    """
    entries = []
    for rec in records:
        entries.append({
            "entry": rec.get("entry"),
            "intent": rec.get("intent_id"),
            "items": [
                {
                    "relation": classify(c),
                    "rank": c.get("rank"),
                    "id": c.get("id"),
                    "evidence": c.get("evidence", []),
                }
                for c in rec.get("candidates", [])
            ],
        })
    return {
        "taken_at": taken_at,
        "independence": independence,
        "entries": entries,
    }


if __name__ == "__main__":
    # 离线自检：用合成记录走一遍"映射 + 转 payload"，不联网。
    demo_records = [{
        "entry": "演示入口",
        "intent_id": "通勤鞋",
        "candidates": [
            {"id": "c1", "rank": 1, "is_paid_labeled": True, "is_affiliated": False,
             "is_suspected_paid": False, "evidence": []},
            {"id": "c2", "rank": 2, "is_paid_labeled": False, "is_affiliated": False,
             "is_suspected_paid": True, "evidence": ["落地页带投放参数"]},
            {"id": "c3", "rank": 3, "is_paid_labeled": False, "is_affiliated": False,
             "is_suspected_paid": False, "evidence": []},
        ],
    }]
    import json
    print(json.dumps(to_measure_payload(demo_records, taken_at="2026-10-10T00:00:00Z"),
                     ensure_ascii=False, indent=2))
