# -*- coding: utf-8 -*-
"""把'变异判据'套用到定版的 13 条自检上：逐条给出 L0/L1/L2 评级"""
import os, json, hashlib, tempfile, importlib.util
here = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("mv", os.path.join(here, "measure_v21定版.py"))
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
base = {"taken_at": "2026-10-10T00:00:00Z"}

print("=" * 78)
print("定版 13 条自检 · 变异判据逐条评级")
print("=" * 78)
print("L0=恒真(啥都没验) L1=验结果(可能被无关差异蒙混) L2=验机制(拆掉机制必失败)\n")

rows = []
def R(n, name, level, note):
    rows.append((n, name, level, note))
    print(f"[{level}] {n:>2} {name}\n      {note}\n")

# 1 基本占比 —— 能不能拆掉'分子计数'？把 independent 不计入 non，overall 应改变
r = M.compute({**base, "entries": [{"entry": "A", "intent": "通勤鞋", "items": [
    {"relation": "independent"}, {"relation": "marked_paid"},
    {"relation": "affiliate"}, {"relation": "independent"}]}]})
R(1, "基本占比", "L1",
  f"断言 overall==0.5。只验结果；未做'把 independent 计数删掉'的对照。"
  f"实测 overall={r['openness_overall']}")

# 2 疑似单列
r = M.compute({**base, "entries": [{"entry": "A", "intent": "x", "items": [
    {"relation": "suspected_paid"}, {"relation": "independent"}]}]})
R(2, "疑似单列", "L1",
  f"断言 suspected_paid==1 且 overall==0.5。实测 overall={r['openness_overall']}。"
  "可拆：把 suspected 并入 non，则 overall 变 1.0 —— 但自检没做这个对照")

# 3 空样本
r = M.compute({**base, "entries": [{"entry": "A", "intent": "y", "items": []}]})
R(3, "空样本⇒不可核", "L1",
  f"实测 uncomputable={r['uncomputable']} overall={r['openness_overall']}。验结果")

# 4 全未知 ⇒ 不可核
r = M.compute({**base, "entries": [{"entry": "A", "intent": "z", "items": [{"relation": "mystery"}] * 4}]})
R(4, "全未知⇒不可核", "L2-",
  f"实测 overall={r['openness_overall']}。★ 这条的'变异'是现成的："
  "把 unknown_max 改成 1.0（等于不设限）⇒ 立刻报 0.0 ⇒ 自检会 FAIL。"
  "★ 但自检没固定阈值，故只有在'有人改了常量'时才暴露——不是主动变异")

# 5 分布：两极 vs 均匀
r = M.compute({**base, "entries": [
    {"entry": "P", "intent": "i", "items": [{"relation": "independent"}] * 2},
    {"entry": "Q", "intent": "i", "items": [{"relation": "marked_paid"}] * 2}]})
R(5, "分布可辨(两极≠均匀)", "L1",
  f"实测 overall={r['openness_overall']} spread={r['spread']}。断言 spread==1.0，验结果")

# 6 自证拒收
r = M.compute({**base, "independence": "provided_by_entry",
               "entries": [{"entry": "A", "intent": "i", "items": [{"relation": "independent"}]}]})
R(6, "自证⇒无 openness", "L2-",
  f"实测 suppressed={r.get('suppressed')} overall={r['openness_overall']}。"
  "★ 这条最接近 L2：把源码里的 suppressed 分支删掉，自检必 FAIL。但没有主动做这个对照")

# 7 改常量 ⇒ 口径指纹变
f1 = M._caliber_fingerprint()
M.CALIBER["consistency_tol"] = 0.5
f2 = M._caliber_fingerprint()
M.CALIBER["consistency_tol"] = 0.05
R(7, "改常量⇒口径指纹变", "L2",
  f"实测 f1={f1} f2={f2} 不同。★ 这条是 L2：它真的改了常量再比，"
  "是'变异对照'的雏形（定版自称'换掉恒真断言'，此条确实做到了）")

# 8 样本不足 —— r 来自第 8 条自己的用例
r = M.compute({**base, "entries": [{"entry": "A", "intent": "i", "items": [{"relation": "independent"}]}]})
R(8, "样本不足提示", "L0-",
  f"仅断言 flags 含'样本不足'。1 条样本必 <40，恒成立 ⇒ 近乎 L0")

# 9 单入口 ⇒ 无分布提示 —— 复用第 8 条的 r ★
R(9, "单入口⇒无分布提示", "L0-",
  "★ 复用第 8 条的 r（单入口、1 条样本）。单入口必然 spread=None ⇒ 必然报'无分布'"
  "⇒ 这条在本用例下恒真；且与第 8 条共用数据，互相污染")

# 10 读数指纹含分布
u = M.compute({**base, "entries": [
    {"entry": "P", "intent": "i", "items": [{"relation": "independent"}] * 2},
    {"entry": "Q", "intent": "i", "items": [{"relation": "independent"}] * 2}]})
v = M.compute({**base, "entries": [
    {"entry": "P", "intent": "i", "items": [{"relation": "independent"}] * 2},
    {"entry": "Q", "intent": "i", "items": [{"relation": "marked_paid"}] * 2}]})
R(10, "均匀与两极⇒读数指纹不同", "❌ 实测 FAIL",
  f"实测 u.overall={u['openness_overall']} v.overall={v['openness_overall']}"
  " —— 断言要求两者都==0.5，但 u 实际=1.0（用例把'均匀'写成了'双极'）"
  " ⇒ ★ 该自检【正常运行就没通过】；就算修对数据，也只是'两枚哈希不等'(L1)，无变异对照")

# 11 compare 遇残件
def _w(obj):
    p = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    json.dump(obj, p); p.close(); return p.name
full = M.compute({**base, "entries": [
    {"entry": "P", "intent": "i", "items": [{"relation": "independent"}] * 25},
    {"entry": "Q", "intent": "i", "items": [{"relation": "independent"}] * 25}]})
pa, pb = _w(full), _w({"openness_overall": 0.5})
out = M.compare(pa, pb); os.unlink(pa); os.unlink(pb)
R(11, "compare 遇残件⇒False", "L2-",
  f"实测 out={out.get('comparable')}。★ 但残件用的 part 恰好不含 spread 字段，"
  "所以豁免分支没被触发 ⇒ 该自检【测不到 spread 豁免这个洞】")

# 12 compare 正常路径
pa, pb = _w(full), _w(full)
out = M.compare(pa, pb); os.unlink(pa); os.unlink(pb)
R(12, "compare 正常路径可用", "L1",
  f"实测 comparable={out.get('comparable')} consistent={out.get('consistent')}")

# 13 未知过多与空样本同档
r = M.compute({**base, "entries": [{"entry": "A", "intent": "z", "items": [{"relation": "mystery"}] * 5}]})
R(13, "未知过多与空样本同档", "L1-重复",
  f"实测 overall={r['openness_overall']}。与第 4 条测同一件事，只是样本量 4→5")

print("=" * 78)
print("汇总")
print("=" * 78)
from collections import Counter
c = Counter(r[2] for r in rows)
for k, v in sorted(c.items()):
    print(f"  {k:>12} : {v} 条")
print()
print("★ 真正达到 L2(变异对照)的只有第 7 条。")
print("★ 第 10 条实测直接 FAIL，是'十三条可过'不成立的唯一硬伤。")
print("★ 第 9/8/13 条存在恒真/复用/重复问题。")
print("★ 第 5、11 条只验结果，第 11 条还恰好绕开了 spread 豁免洞。")
