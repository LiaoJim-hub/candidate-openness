# -*- coding: utf-8 -*-
"""变异测试：证明自检 10 是'验结果不验机制'，并找出唯一能抓住机制的写法"""
import os, json, hashlib, importlib.util
here = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("mv", os.path.join(here, "measure_v21定版.py"))
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
base = {"taken_at": "2026-10-10T00:00:00Z"}

def line(t): print("\n" + "=" * 64 + "\n" + t + "\n" + "=" * 64)

# 正确构造：均匀(每入口0.5) vs 两极(1.0/0.0)，overall 同 0.5，samples 同
uni = M.compute({**base, "entries": [
    {"entry": "P", "intent": "i", "items": [{"relation": "independent"}, {"relation": "marked_paid"}]},
    {"entry": "Q", "intent": "i", "items": [{"relation": "independent"}, {"relation": "marked_paid"}]}]})
pol = M.compute({**base, "entries": [
    {"entry": "P", "intent": "i", "items": [{"relation": "independent"}] * 2},
    {"entry": "Q", "intent": "i", "items": [{"relation": "marked_paid"}] * 2}]})
print("均匀: overall=%s per_entry=%s spread=%s" % (uni["openness_overall"], uni["per_entry_openness"], uni["spread"]))
print("两极: overall=%s per_entry=%s spread=%s" % (pol["openness_overall"], pol["per_entry_openness"], pol["spread"]))

line("变异 1：把 per_entry / spread 从 basis 里【删掉】")
def fp_mutant(r):
    basis = json.dumps({"caliber": r["caliber_fingerprint"],
                        "overall": r["openness_overall"],
                        "samples": r["samples"]}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]
mu, mp = fp_mutant(uni), fp_mutant(pol)
print("变异后 均匀 fp =", mu, " 两极 fp =", mp)
print("两枚相同:", mu == mp)
print("→ 变异后【完全相同】。也就是说：")
print("   若有人把 per_entry/spread 从 basis 删掉，用【同一条断言】'u'!='v' 的写法")
print("   ——断言会【失败】（因为相等）—— 咦，那这条断言其实能抓住变异？")
print("   ★ 不。原因：定版自检10 用的是【错的数据】u（overall 都=1.0），")
print("     而非 overall 相同的正确对照组。见下。")

line("变异 2：定版实际用的那组数据，在'删掉分布'后的表现")
u_act = M.compute({**base, "entries": [      # 定版的 u：两入口都全 independent
    {"entry": "P", "intent": "i", "items": [{"relation": "independent"}] * 2},
    {"entry": "Q", "intent": "i", "items": [{"relation": "independent"}] * 2}]})
v_act = M.compute({**base, "entries": [      # 定版的 v：一入口全独立、一入口全付费
    {"entry": "P", "intent": "i", "items": [{"relation": "independent"}] * 2},
    {"entry": "Q", "intent": "i", "items": [{"relation": "marked_paid"}] * 2}]})
print("u overall=%.2f spread=%s | v overall=%.2f spread=%s"
      % (u_act["openness_overall"], u_act["spread"], v_act["openness_overall"], v_act["spread"]))
mua, mva = fp_mutant(u_act), fp_mutant(v_act)
print("变异后 u fp =", mua, " v fp =", mva, " 相同:", mua == mva)
print("→ 【相同】！也就是说：定版自检10 的数据对，在'把分布机制整个删掉'之后，")
print("   'u'!='v' 这条断言【仍然成立】？不——它会失败（因为相同）——")
print("   ★ 注意：定版原来的断言在【未变异】时就已经 FAIL 了（overall 不等），")
print("     所以这条自检根本没跑到'验机制'那一步。它连【正常运行】都没通过。")

line("★ 决定性：一条'能抓机制'的自检应该长什么样（变异测试才是判据）")
def selftest10_good(mutate=False):
    """返回 True 表示通过。mutate=True 模拟'有人删掉 per_entry/spread'。"""
    U = {**base, "entries": [
        {"entry": "P", "intent": "i", "items": [{"relation": "independent"}, {"relation": "marked_paid"}]},
        {"entry": "Q", "intent": "i", "items": [{"relation": "independent"}, {"relation": "marked_paid"}]}]}
    V = {**base, "entries": [
        {"entry": "P", "intent": "i", "items": [{"relation": "independent"}] * 2},
        {"entry": "Q", "intent": "i", "items": [{"relation": "marked_paid"}] * 2}]}
    ru, rv = M.compute(U), M.compute(V)
    if mutate:
        fu, fv = fp_mutant(ru), fp_mutant(rv)
    else:
        fu, fv = ru["reading_fingerprint"], rv["reading_fingerprint"]
    # ★ 关键：两件事一起断言 —— 前提(overall/samples 必须相同) + 机制(指纹必须不同)
    return (ru["openness_overall"] == rv["openness_overall"] == 0.5
            and ru["samples"] == rv["samples"]
            and ru["per_entry_openness"] != rv["per_entry_openness"]     # 分布确实不同
            and fu != fv)                                                # 指纹因此必须不同

print("未变异 → 通过:", selftest10_good(mutate=False))
print("已变异（删掉分布）→ 通过:", selftest10_good(mutate=True))
print()
print("★★ 这才是'验机制'：删掉被测机制 ⇒ 自检必须失败。")
print("   定版的 chk(10)：① 用例构造错（overall 不等，正常跑就 FAIL）；")
print("   ② 就算改对了数据，它也只是断言'两枚哈希不等'——")
print("      而【任何不同输入都会哈希不等】，它没做'删掉机制后必失败'的对照。")
print()
print("   结论一句话：定版报告自己设的验收标准（§六表格第5行'变异测试'）")
print("   —— 它给了标准，但没把标准用在自检10 上。")
