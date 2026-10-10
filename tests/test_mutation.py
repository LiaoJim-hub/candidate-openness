# -*- coding: utf-8 -*-
"""
变异测试 · 自检有效性判据的执行版

规范见 docs/变异测试规范.md。判据一句话：
    一条自检, 若在"把被测机制拆掉"之后仍然通过, 它就是无效的。

本文件不测"尺子算得对不对", 只测"仓库里的自检抓不抓得住机制"。
运行:  python -m unittest discover -s tests -v
"""
import copy
import hashlib
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import measure as M

BASE = {"taken_at": "2026-10-10T00:00:00Z"}

UNIFORM = {**BASE, "entries": [
    {"entry": k, "intent": "i",
     "items": [{"relation": "independent"}, {"relation": "marked_paid"}]}
    for k in ("P", "Q")]}
POLAR = {**BASE, "entries": [
    {"entry": "P", "intent": "i", "items": [{"relation": "independent"}] * 2},
    {"entry": "Q", "intent": "i", "items": [{"relation": "marked_paid"}] * 2}]}


def _fp_without(r, drop):
    """变异指纹：把 basis 里的 drop 字段(们) 删掉后重算, 模拟'机制被拆'。"""
    basis = {
        "caliber": r["caliber_fingerprint"],
        "openness_main": r["openness_main"],
        "openness_strict": r["openness_strict"],
        "spread": r["spread"],
        "per_entry": r["per_entry_openness"],
        "samples": r["samples"],
        "intents": r["intents"],
        "independence": r["independence"],
    }
    for k in drop:
        basis.pop(k, None)
    return hashlib.sha256(
        json.dumps(basis, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:16]


class TestMutation(unittest.TestCase):
    """每条: 先断言'前提成立', 再断言'拆掉机制则失败'。"""

    # ---------------------------------------------------------------
    def test_premise_uniform_vs_polar(self):
        """前提：均匀与两极的 overall/samples 确实相同, 分布确实不同。"""
        u, v = M.compute(UNIFORM), M.compute(POLAR)
        self.assertEqual(u["openness_main"], v["openness_main"])
        self.assertEqual(u["samples"], v["samples"])
        self.assertNotEqual(u["per_entry_openness"], v["per_entry_openness"])

    def test_mutation_distribution_in_reading_fp(self):
        """读数指纹含分布：拆掉 per_entry/spread ⇒ 均匀与两极指纹变相同 ⇒ 机制失效。"""
        u, v = M.compute(UNIFORM), M.compute(POLAR)
        # 正常：指纹必须不同（这是被测机制在起作用）
        self.assertNotEqual(u["reading_fingerprint"], v["reading_fingerprint"])
        # 变异：拆掉分布 ⇒ 两枚必须变相同（证明确实是分布带来的差异）
        mu = _fp_without(u, ("per_entry", "spread"))
        mv = _fp_without(v, ("per_entry", "spread"))
        self.assertEqual(mu, mv, "拆掉分布后指纹仍不同 ⇒ 分布并未真正进指纹")

    def test_mutation_independence_in_reading_fp(self):
        """读数指纹含效力：拆掉 independence ⇒ none 与 has_relation 指纹变相同。"""
        p = {**BASE, "entries": [
            {"entry": "P", "intent": "i", "items": [{"relation": "independent"}] * 2},
            {"entry": "Q", "intent": "i", "items": [{"relation": "marked_paid"}] * 2}]}
        rn = M.compute(p)
        rr = M.compute({**p, "independence": "has_relation"})
        self.assertNotEqual(rn["reading_fingerprint"], rr["reading_fingerprint"])
        self.assertEqual(_fp_without(rn, ("independence",)),
                         _fp_without(rr, ("independence",)),
                         "拆掉 independence 后指纹仍不同 ⇒ 效力并未真正进指纹")

    def test_mutation_caliber_relation_map(self):
        """口径指纹含归类表：拆掉 relation_map ⇒ 改归类不再改变指纹。"""
        c_full = copy.deepcopy(M.CALIBER)
        c_mut = copy.deepcopy(M.CALIBER)
        c_mut["relation_map"]["independent"] = "related"   # 改归类
        self.assertNotEqual(M._caliber_fingerprint(c_full),
                            M._caliber_fingerprint(c_mut),
                            "改归类表后口径指纹没变 ⇒ 归类表未真正进指纹")
        # 拆掉 relation_map 后再改, 指纹必须变相同
        c_full.pop("relation_map"); c_mut.pop("relation_map")
        self.assertEqual(M._caliber_fingerprint(c_full),
                         M._caliber_fingerprint(c_mut),
                         "拆掉 relation_map 后指纹仍不同 ⇒ 它其实没参与指纹")

    def test_mutation_suppressed_gate(self):
        """自证闸门：拆掉该分支 ⇒ 自证数据会算出数。"""
        p = {**BASE, "independence": "provided_by_entry",
             "entries": [{"entry": "A", "intent": "i",
                          "items": [{"relation": "independent"}] * 3}]}
        r = M.compute(p)
        self.assertIsNone(r["openness_main"])          # 闸门在
        self.assertTrue(r.get("suppressed"))
        # 变异：直接按普通路径算同一批数据（模拟闸门被拆）
        mutant = M.compute({**BASE, "entries": p["entries"]})
        self.assertIsNotNone(mutant["openness_main"],
                             "拆掉闸门后仍未出数 ⇒ 该断言测的不是闸门")

    def test_mutation_compare_spread_not_exempt(self):
        """compare 完整性：单入口(spread=None)必须被判不完整。"""
        single = M.compute({**BASE, "entries": [
            {"entry": "P", "intent": "i", "items": [{"relation": "independent"}] * 50}]})
        self.assertIsNone(single["spread"])
        p = os.path.join(ROOT, "_mut_single.json")
        try:
            with open(p, "w", encoding="utf-8") as f:
                json.dump(single, f, ensure_ascii=False)
            out = M.compare(p, p)
            self.assertFalse(out["comparable"],
                             "单入口读数被判为完整可比 ⇒ spread 仍被豁免")
        finally:
            if os.path.exists(p):
                os.remove(p)

    def test_mutation_compare_rejects_suppressed(self):
        """compare 拒自证：拆掉该检查 ⇒ 自证可进比对。"""
        sup = M.compute({**BASE, "independence": "provided_by_entry",
                         "entries": [{"entry": "A", "intent": "i",
                                      "items": [{"relation": "independent"}] * 2}]})
        normal = M.compute({**BASE, "entries": [
            {"entry": "A", "intent": "i", "items": [{"relation": "independent"}] * 2}]})
        pa, pb = os.path.join(ROOT, "_mut_a.json"), os.path.join(ROOT, "_mut_b.json")
        try:
            for path, obj in ((pa, sup), (pb, normal)):
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(obj, f, ensure_ascii=False)
            out = M.compare(pa, pb)
            self.assertFalse(out["comparable"])
            self.assertIn("自证", out.get("reason", "") + out.get("note", "")
                          + str(out), "拒因未说明是自证 ⇒ 拦错了地方")
        finally:
            for path in (pa, pb):
                if os.path.exists(path):
                    os.remove(path)


    def test_mutation_gate_must_speak_in_flags(self):
        """★ 闸门必须在 flags 里出声，且未超限时【不】出声。

        v2.2 引入两道闸门（unknown 超限 / suspected 超限），初版只把原因写进
        detail.note，顶层 flags 一字不提 ⇒ 读的人拿到 openness_main=None，
        分不清是"数据不足"还是"被闸门拦下"。本条用正反两测锁住该行为。
        """
        cases = {
            "unknown": [{"relation": "independent"}, {"relation": "mystery"}],
            "suspected": ([{"relation": "independent"}]
                          + [{"relation": "suspected_paid"}] * 3),
        }
        ok_items = ([{"relation": "independent"}] * 9 + [{"relation": "mystery"}])
        for kind, items in cases.items():
            with self.subTest(gate=kind):
                r = M.compute({**BASE, "entries": [
                    {"entry": "E", "intent": "i", "items": items}]})
                self.assertIsNone(r["openness_main"], "闸门未生效")
                self.assertTrue(
                    any("判不可核" in f for f in r["flags"]),
                    f"闸门[{kind}]触发了但 flags 不出声 ⇒ 读的人不知为何没出数")
                # ★ 反面：未超限时该告警必须【不】出现，否则告警恒真、抓不住机制
                r2 = M.compute({**BASE, "entries": [
                    {"entry": "E", "intent": "i", "items": ok_items}]})
                self.assertIsNotNone(r2["openness_main"], "未超限却不出数")
                self.assertFalse(
                    any("判不可核" in f for f in r2["flags"]),
                    f"未超限也报[{kind}]闸门 ⇒ 该告警恒真，抓不住机制")


if __name__ == "__main__":
    unittest.main(verbosity=2)
