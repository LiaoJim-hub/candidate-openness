# -*- coding: utf-8 -*-
"""
单元测试 · 候选集开放度尺子

运行:  python -m unittest discover -s tests -v
"""
import copy
import json
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "adapters"))

import measure as M            # noqa: E402
import example_adapter as A    # noqa: E402

BASE = {"taken_at": "2026-10-10T00:00:00Z"}


class TestMeasure(unittest.TestCase):

    # --- 基本口径 ------------------------------------------------
    def test_basic_ratio(self):
        r = M.compute({**BASE, "entries": [{"entry": "A", "intent": "通勤鞋", "items": [
            {"relation": "independent"}, {"relation": "marked_paid"},
            {"relation": "affiliate"}, {"relation": "independent"}]}]})
        self.assertEqual(r["openness_main"], 0.5)
        self.assertEqual(r["openness_strict"], 0.5)

    def test_main_vs_strict(self):
        # ★★ 2026-10-10 改（持有方定义判）：疑似**单列** —— 不进分子、**也不进分母**。
        #   ★ 故 1 独立 + 1 疑似 ⇒ 分母 = 1（只含观测到的）· 分子 = 1 ⇒ 主/严格**都 = 1.0**
        #   ★ 而"疑似那个量"由 `suspected_paid` / `suspected_rate` **单列报出** ⇒
        #     只报一个 `openness_main` = **不完整读数**（本仓 README「报数纪律」）。
        r = M.compute({**BASE, "entries": [{"entry": "A", "intent": "x", "items": [
            {"relation": "suspected_paid"}, {"relation": "independent"}]}]})
        self.assertEqual(r["openness_main"], 1.0)
        self.assertEqual(r["openness_strict"], 1.0)
        self.assertEqual(r["openness_overall"], r["openness_main"])  # 别名
        self.assertEqual(r["suspected_paid"], 1)
        self.assertEqual(r["suspected_rate"], 0.5)          # ★ 那个量必须同时报
        self.assertEqual(r["samples"], 2)                    # ★ 样本量仍含疑似（它没被丢掉）

    def test_empty_is_uncomputable(self):
        r = M.compute({**BASE, "entries": [{"entry": "A", "intent": "y", "items": []}]})
        self.assertEqual(r["uncomputable"], 1)
        self.assertIsNone(r["openness_main"])
        self.assertTrue(r["entries_without_data"])

    def test_unknown_relation_flagged(self):
        # ★★ 2026-10-10 改：未知**超限即不可核**（持有方定义判）。
        #   ★ 故用"未超限"的样本（4 已知 + 1 未知 = 恰 20%）验"词表照报"；
        #   ★ 而"超限"那一路另有一条测试（test_unknown_over_limit_uncomputable）。
        r = M.compute({**BASE, "entries": [{"entry": "A", "intent": "z", "items": [
            {"relation": "independent"}] * 4 + [{"relation": "mystery"}]}]})
        self.assertEqual(r["uncomputable"], 0)
        # ★ 分母只含观测到的 ⇒ 4/4 = 1.0（未知不进分母，与疑似同待遇）
        self.assertEqual(r["openness_main"], 1.0)
        self.assertEqual(r["unknown_relations"], ["mystery"])
        self.assertTrue(any("未识别" in f for f in r["flags"]))

    def test_unknown_over_limit_uncomputable(self):
        # ★★ 2026-10-10 加：★ 未知占比超 `UNKNOWN_MAX`(0.2) ⇒ **该入口整体不可核**
        r = M.compute({**BASE, "entries": [{"entry": "A", "intent": "z0", "items": [
            {"relation": "independent"}, {"relation": "mystery"}]}]})
        self.assertEqual(r["uncomputable"], 1)
        self.assertIsNone(r["openness_main"])
        # ★ 而**不可核那一路也必须交未知词表**（否则拼错的 relation 反而看不见）
        self.assertEqual(r["unknown_relations"], ["mystery"])

    def test_spread_polar_vs_uniform(self):
        r = M.compute({**BASE, "entries": [
            {"entry": "P", "intent": "i", "items": [{"relation": "independent"}] * 2},
            {"entry": "Q", "intent": "i", "items": [{"relation": "marked_paid"}] * 2}]})
        self.assertEqual(r["openness_main"], 0.5)
        self.assertEqual(r["spread"], 1.0)

    # --- 效力 / 自证 ---------------------------------------------
    def test_provided_by_entry_excluded_from_aggregate(self):
        r = M.compute({**BASE, "independence": "provided_by_entry",
                       "entries": [{"entry": "A", "intent": "i",
                                    "items": [{"relation": "independent"}] * 3}]})
        self.assertEqual(r["effect"], "不算独立读数")
        self.assertIsNone(r["openness_main"])               # 不入聚合
        self.assertEqual(len(r["excluded_from_aggregate"]), 1)
        self.assertTrue(any("不参与聚合" in f for f in r["flags"]))

    def test_compare_rejects_non_independent(self):
        a = M.compute({**BASE, "independence": "has_relation",
                       "entries": [{"entry": "E", "intent": "i",
                                    "items": [{"relation": "independent"}] * 2}]})
        b = M.compute({**BASE, "entries": [{"entry": "E", "intent": "i",
                                            "items": [{"relation": "independent"}] * 2}]})
        pa, pb = os.path.join(ROOT, "_t_a.json"), os.path.join(ROOT, "_t_b.json")
        try:
            with open(pa, "w", encoding="utf-8") as f:
                json.dump(a, f, ensure_ascii=False)
            with open(pb, "w", encoding="utf-8") as f:
                json.dump(b, f, ensure_ascii=False)
            out = M.compare(pa, pb)
            self.assertFalse(out["comparable"])
        finally:
            for p in (pa, pb):
                if os.path.exists(p):
                    os.remove(p)

    # --- 指纹敏感性 ----------------------------------------------
    def test_caliber_fingerprint_sensitive_to_logic(self):
        c2 = copy.deepcopy(M.CALIBER)
        c2["relation_map"]["independent"] = "related"
        self.assertNotEqual(M._caliber_fingerprint(c2), M._caliber_fingerprint())

    def test_reading_fingerprint_sensitive_to_distribution(self):
        uniform = {**BASE, "entries": [
            {"entry": k, "intent": "i",
             "items": [{"relation": "independent"}, {"relation": "marked_paid"}]}
            for k in ("A", "B", "C", "D")]}
        polar = {**BASE, "entries": [
            {"entry": "P", "intent": "i", "items": [{"relation": "independent"}] * 4},
            {"entry": "Q", "intent": "i", "items": [{"relation": "marked_paid"}] * 4}]}
        ru, rp = M.compute(uniform), M.compute(polar)
        self.assertEqual(ru["openness_main"], rp["openness_main"])
        self.assertNotEqual(ru["reading_fingerprint"], rp["reading_fingerprint"])

    def test_reading_fingerprint_sensitive_to_independence(self):
        p = {**BASE, "entries": [{"entry": "A", "intent": "i",
                                  "items": [{"relation": "independent"}] * 2}]}
        self.assertNotEqual(M.compute(p)["reading_fingerprint"],
                            M.compute({**p, "independence": "has_relation"})["reading_fingerprint"])

    # --- CLI -----------------------------------------------------
    def test_cli_aliases_and_version(self):
        fixture = os.path.join(ROOT, "examples", "selftest_fixture.json")
        for flag in ("--in", "--input"):
            p = subprocess.run([sys.executable, os.path.join(ROOT, "measure.py"),
                                flag, fixture], capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
        p = subprocess.run([sys.executable, os.path.join(ROOT, "measure.py"), "--version"],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0)
        self.assertIn(M.PROTOCOL_VERSION, p.stdout)

    def test_cli_friendly_error(self):
        p = subprocess.run([sys.executable, os.path.join(ROOT, "measure.py"),
                            "--in", "definitely_missing.json"], capture_output=True, text=True)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("找不到文件", p.stdout + p.stderr)


class TestAdapter(unittest.TestCase):
    def test_classify_priority(self):
        self.assertEqual(A.classify({"is_paid_labeled": True, "is_suspected_paid": True}), "marked_paid")
        self.assertEqual(A.classify({"is_paid_labeled": False, "is_suspected_paid": True}), "suspected_paid")
        self.assertEqual(A.classify({"is_paid_labeled": False, "is_suspected_paid": False,
                                     "is_affiliated": True}), "affiliate")
        self.assertEqual(A.classify({}), "independent")

    def test_to_payload_roundtrip(self):
        recs = [{"entry": "E", "intent_id": "通勤鞋", "candidates": [
            {"id": "1", "is_paid_labeled": True},
            {"id": "2", "is_paid_labeled": False, "is_affiliated": False,
             "is_suspected_paid": False}]}]
        payload = A.to_measure_payload(recs, taken_at=BASE["taken_at"])
        r = M.compute(payload)
        self.assertEqual(r["openness_main"], 0.5)
        self.assertEqual(r["openness_strict"], 0.5)

    def test_fetch_is_not_implemented(self):
        with self.assertRaises(NotImplementedError):
            A.fetch_candidates("通勤鞋", {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
