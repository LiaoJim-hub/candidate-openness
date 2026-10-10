# -*- coding: utf-8 -*-
"""v2.1 定版 对抗探测"""
import json, os, sys, copy
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib.util
spec = importlib.util.spec_from_file_location(
    "mv", os.path.join(os.path.dirname(os.path.abspath(__file__)), "measure_v21定版.py"))
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)

def line(t): print("\n" + "=" * 64 + "\n" + t + "\n" + "=" * 64)
base = {"taken_at": "2026-10-10T00:00:00Z"}

# ====================================================================
line("D0  自检 10 的真实失败原因（逐字段拆解）")
u = M.compute({**base, "entries": [
    {"entry": "P", "intent": "i", "items": [{"relation": "independent"}] * 2},
    {"entry": "Q", "intent": "i", "items": [{"relation": "independent"}] * 2}]})
v = M.compute({**base, "entries": [
    {"entry": "P", "intent": "i", "items": [{"relation": "independent"}] * 2},
    {"entry": "Q", "intent": "i", "items": [{"relation": "marked_paid"}] * 2}]})
print("u: overall=%s per_entry=%s spread=%s samples=%s fp=%s"
      % (u["openness_overall"], u["per_entry_openness"], u["spread"], u["samples"], u["reading_fingerprint"]))
print("v: overall=%s per_entry=%s spread=%s samples=%s fp=%s"
      % (v["openness_overall"], v["per_entry_openness"], v["spread"], v["samples"], v["reading_fingerprint"]))
print("\n★ 自检10 假设 '均匀=每入口0.5, 两极=一入口1.0一入口0.0, 两者 overall 都是0.5'")
print("  但它写的数据 u 是【两个入口都全 independent】= 两极(1.0/1.0, spread=0) 而非均匀")
print("  真实差异: u.overall=%s v.overall=%s  —— overall 根本不相等，断言第一半就假"
      % (u["openness_overall"], v["openness_overall"]))
print("  ⇒ 这不是'机制失效'，是【测试用例构造错了】：把'均匀'写成了'双极'")

# ====================================================================
line("D1  【P0】compare 的 spread 豁免：单入口残件被判为完整可引用")
single = M.compute({**base, "entries": [
    {"entry": "P", "intent": "i", "items": [{"relation": "independent"}] * 50}]})
print("单入口读数 spread =", single["spread"], " flags =", single["flags"])
p1 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "s1.json")
json.dump(single, open(p1, "w", encoding="utf-8"), ensure_ascii=False)
out = M.compare(p1, p1)
print("compare(单入口, 单入口) =", json.dumps(out, ensure_ascii=False))
print("→ 源码第232行: `f not in (\"spread\",)` 明确豁免了 spread ⇒ 协议§4说'单入口无分布'，"
      "compare 却放行，同一份读数两套标准")

# ====================================================================
line("D2  【P0】has_relation 不进读数指纹（与定版§1修正6/§4第5节声明冲突）")
p = {**base, "entries": [{"entry": "P", "intent": "i",
                          "items": [{"relation": "independent"}] * 2},
                         {"entry": "Q", "intent": "i",
                          "items": [{"relation": "marked_paid"}] * 2}]}
r_none = M.compute(p)
r_rel = M.compute({**p, "independence": "has_relation"})
print("none         effect=%-8s fp=%s" % (r_none["effect"], r_none["reading_fingerprint"]))
print("has_relation effect=%-8s fp=%s" % (r_rel["effect"], r_rel["reading_fingerprint"]))
print("两枚指纹相同:", r_none["reading_fingerprint"] == r_rel["reading_fingerprint"])
print("→ basis 里没有 independence 字段（源码204-211行）")

# ====================================================================
line("D3  【P0】判定阈值读全局 CALIBER，非该次运行冻结值（'同数据不同判定'）")
data = {**base, "entries": [
    {"entry": "P", "intent": "i", "items": [{"relation": "independent"}] * 30},
    {"entry": "Q", "intent": "i", "items": [{"relation": "independent"}] * 30}]}
saved = M.CALIBER["consistency_tol"]
M.CALIBER["consistency_tol"] = 0.5           # 模拟"进程里被人改过"
p2 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "s2.json")
json.dump(M.compute(data), open(p2, "w", encoding="utf-8"), ensure_ascii=False)
M.CALIBER["consistency_tol"] = saved         # 还原
r_dirty = json.load(open(p2, encoding="utf-8"))
r_clean = M.compute(data)
print("污染态 fp =", r_dirty["caliber_fingerprint"], " 干净态 fp =", r_clean["caliber_fingerprint"])
print("指纹相同:", r_dirty["caliber_fingerprint"] == r_clean["caliber_fingerprint"])
# 造一个 0.1 差值的比对，看阈值是否随手改的全局值走
a = M.compute({**base, "entries": [
    {"entry": "P", "intent": "i", "items": [{"relation": "independent"}] * 55},
    {"entry": "Q", "intent": "i", "items": [{"relation": "independent"}] * 45}]})
pa = os.path.join(os.path.dirname(os.path.abspath(__file__)), "s3.json")
json.dump(a, open(pa, "w", encoding="utf-8"), ensure_ascii=False)
M.CALIBER["consistency_tol"] = 0.5
o1 = M.compare(p1, pa)
M.CALIBER["consistency_tol"] = saved
o2 = M.compare(p1, pa)
print("tol=0.5 时 consistent =", o1.get("consistent"), " | tol=0.05 时 consistent =", o2.get("consistent"))
print("→ 同一对文件，仅因进程内 CALIBER 被改，结论翻转；而落盘的 caliber_fingerprint 一字不变")

# ====================================================================
line("D4  【P0】自检 7 自己污染 CALIBER（同进程内改全局常量），若中途 return 则永久改口径")
print("说明：自检7 直接写 CALIBER['consistency_tol']=0.5 再还原。")
print("  ① 该写法在'自检被中断/异常'时会永久污染进程口径；")
print("  ② 更根本：这正是 D3 的成因示范——口径常量是模块级可变全局。")

# ====================================================================
line("D5  【P1】修正4(全未知⇒不可核) 只在'单入口局部'生效，聚合层不校验 unknown")
mk = lambda n: [{"relation": "mystery"}] * n
p = {**base, "entries": [
    {"entry": "P", "intent": "i",
     "items": [{"relation": "independent"}] * 9 + [{"relation": "mystery"}] * 1},  # 10% 未知,通过
    {"entry": "Q", "intent": "i",
     "items": [{"relation": "independent"}] * 9 + [{"relation": "mystery"}] * 1}]}
r = M.compute(p)
print("每入口未知率 10%(<20% 阈值) ⇒ overall =", r["openness_overall"],
      " 合计 unknown =", r["unknown"], "/", r["samples"],
      "= %.2f" % (r["unknown"] / r["samples"]))
print("→ 每个入口都'合规'，但整体未知率仍是 10%；阈值是【每入口】的，没有全局闸。")
print("  更极端：入口数很多时，每入口 19% 未知 ⇒ 全局 19%，但每个入口都放行。")

# ====================================================================
line("D6  【P1】suspected_paid 不进分子、也不进 unknown —— 修正4的'第三类'没有覆盖疑似")
p = {**base, "entries": [{"entry": "P", "intent": "i", "items": [
    {"relation": "suspected_paid"}, {"relation": "independent"}]}]}
r = M.compute(p)
print("items=[suspected, independent] ⇒ overall =", r["openness_overall"],
      "(可疑位被当作分母扣掉)")
print("→ v1.0/README 的口径是'非关联=既非付费位也非关联方'，suspected_paid【没有付费标注】"
      "⇒ 按 README 应进分子；此处被算作不开放。口径又被单方面改了。")
print("  上轮我已就这一点请裁决（主口径含不含疑似），至今未决；v2.1 又独立选了第三种做法。")

# ====================================================================
line("D7  【P1】空样本与'全未知不可核'确实同档 —— 定版自己声称的一致，实测")
r1 = M.compute({**base, "entries": [{"entry": "A", "intent": "y", "items": []}]})
r2 = M.compute({**base, "entries": [{"entry": "A", "intent": "z", "items": mk(5)}]})
print("空样本  : uncomputable=%s overall=%s" % (r1["uncomputable"], r1["openness_overall"]))
print("全未知  : uncomputable=%s overall=%s" % (r2["uncomputable"], r2["openness_overall"]))
print("→ OK，这一条定版做对了")

# ====================================================================
line("D8  【P1】唯一的'防漂白'手段 compare 看 per_entry —— 只打印不判定")
a2 = M.compute({**base, "entries": [
    {"entry": "P", "intent": "i", "items": [{"relation": "independent"}] * 30},
    {"entry": "Q", "intent": "i", "items": [{"relation": "independent"}] * 30}]})
b2 = M.compute({**base, "entries": [
    {"entry": "P", "intent": "i", "items": [{"relation": "independent"}] * 60},
    {"entry": "Q", "intent": "i", "items": [{"relation": "marked_paid"}] * 1 +
                                    [{"relation": "independant"}] * 0}]})
pb = os.path.join(os.path.dirname(os.path.abspath(__file__)), "s4.json")
json.dump(b2, open(pb, "w", encoding="utf-8"), ensure_ascii=False)
o = M.compare(p1, pb)
print("compare 返回键:", list(o.keys()))
print("→ a_per_entry/b_per_entry 只是回显，没有任何'不一致'判定/告警字段。"
      "§8 承认'防漂白不完备'，但连'llm 打印出的分布'都没设一个对比判据。")

# ====================================================================
line("D9  【P1】自检 10 的'反事实'声称：把 per_entry/spread 从 basis 删掉，自检 10 还过吗？")
print("变异测试：模拟'删掉 per_entry 与 spread'后的指纹，看自检10 是否仍通过")
def fp_without_dist(r):
    basis = json.dumps({"caliber": r["caliber_fingerprint"],
                        "overall": r["openness_overall"],
                        "samples": r["samples"]},
                       sort_keys=True, ensure_ascii=False)
    import hashlib
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]
u2 = M.compute({**base, "entries": [
    {"entry": "P", "intent": "i", "items": [{"relation": "independent"}] * 2},
    {"entry": "Q", "intent": "i", "items": [{"relation": "independent"}] * 2}]})
v2 = M.compute({**base, "entries": [
    {"entry": "P", "intent": "i", "items": [{"relation": "independent"}] * 2},
    {"entry": "Q", "intent": "i", "items": [{"relation": "marked_paid"}] * 2}]})
print("（注：正确构造的均匀/两极用例下）")
uni = M.compute({**base, "entries": [
    {"entry": "P", "intent": "i", "items": [{"relation": "independent"}, {"relation": "marked_paid"}]},
    {"entry": "Q", "intent": "i", "items": [{"relation": "independent"}, {"relation": "marked_paid"}]}]})
pol = M.compute({**base, "entries": [
    {"entry": "P", "intent": "i", "items": [{"relation": "independent"}] * 2},
    {"entry": "Q", "intent": "i", "items": [{"relation": "marked_paid"}] * 2}]})
print("均匀: overall=%s per_entry=%s spread=%s" % (uni["openness_overall"], uni["per_entry_openness"], uni["spread"]))
print("两极: overall=%s per_entry=%s spread=%s" % (pol["openness_overall"], pol["per_entry_openness"], pol["spread"]))
print("原指纹不同:", uni["reading_fingerprint"] != pol["reading_fingerprint"])
print("删掉分布后指纹:", fp_without_dist(uni), fp_without_dist(pol),
      " 仍不同:", fp_without_dist(uni) != fp_without_dist(pol))
print("→ ★ 删掉分布后两者还是会不同？不会——若 overall/samples 相同则必相同。")
print("  关键：定版的 chk(10) 只是'两枚哈希不等'，它【没有】做'删掉机制后必失败'的变异对照。")
print("  它自检7 做了变异对照（改常量⇒指纹变），自检10 却只是断言不等 ⇒ 仍是'验结果不验机制'。")

# ====================================================================
line("D10 【P2】CLI / 异常 / 死代码 / 重复量")
print("① CLI 仍只有 --in/--out，README 若写 --input/--output 则不符（v2.0 的老问题）")
print("② json.load(open(...)) 裸开文件：文件缺失/坏 JSON ⇒ 裸 traceback")
print("③ _rate 返回的 'openness' 字段全篇无人使用（死代码）")
print("④ 自检 4 与自检 13 测的是同一件事（全未知⇒不可核），重复")
print("⑤ 自检 9 复用自检 8 的 r（1 条 independent 的单入口），只是换断言——耦合")
print("⑥ CALIBER['reading_anchor'] 声明了锚 overall/per_entry/spread，但代码【不校验】"
      "basis 是否真含这三项 ⇒ '报什么锚什么'无闸门，纯注释")

print("\n" + "=" * 64)
print("探测结束")
