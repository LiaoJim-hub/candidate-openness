# -*- coding: utf-8 -*-
"""对抗性探测：找 v2.0 实现与协议不一致 / 可误用点"""
import json, hashlib
import measure_v20 as M

def line(t): print("\n" + "=" * 62 + "\n" + t + "\n" + "=" * 62)

base = {"taken_at": "2026-10-10T00:00:00Z"}

# ---------------------------------------------------------------- P1
line("P1  provided_by_entry 是否真的‘不入聚合’？（PROTOCOL 第8节声称拒收）")
p = {**base, "independence": "provided_by_entry",
     "entries": [{"entry": "某平台", "intent": "通勤鞋", "items": [
         {"relation": "independent"}, {"relation": "marked_paid"}]}]}
r = M.compute(p)
print("effect          =", r["effect"])
print("openness_overall=", r["openness_overall"], "  ← 协议说‘不算独立读数、不入聚合’，这里却照样算出了总读数")
print("samples         =", r["samples"])
print("per_entry       =", r["per_entry_openness"])

# ---------------------------------------------------------------- P2
line("P2  openness_overall 到底是‘主口径’还是‘严格口径’？")
p = {**base, "entries": [{"entry": "A", "intent": "x", "items": [
    {"relation": "suspected_paid"}, {"relation": "independent"}]}]}
r = M.compute(p)
# 主口径(README v1.0)：非付费标注 且 非关联 → 疑似(无付费标注)也算“非关联”→ 1.0
# 严格口径：再扣疑似 → 0.5
print("openness_overall =", r["openness_overall"], "（v2.0 实际值）")
print("主口径(README v1.0)= 1.0  严格口径= 0.5")
print("→ v2.0 的 overall 静默等于【严格口径】，README 承诺的‘主/严格并列’没了")

# ---------------------------------------------------------------- P3
line("P3  指纹真的‘改任何一条口径规则必变’吗？"
     "（把‘独立’改判成‘关联’——即改计算逻辑，不碰 CALIBER 常量）")
print("原 CALIBER 指纹 =", M._caliber_fingerprint())
# 模拟：有人把 independent 也从分子里拿掉（改逻辑），CALIBER 未动
CALIBER_BEFORE = dict(M.CALIBER)
def _rate_modified(items):
    return {"total": len(items), "non_related": 0,
            "suspected_paid": 0, "openness": 0.0}
orig = M._rate
M._rate = _rate_modified
r2 = M.compute({**base, "entries": [{"entry": "A", "intent": "x",
                                     "items": [{"relation": "independent"}]}]})
print("改逻辑后 overall =", r2["openness_overall"], "  指纹 =", r2["caliber_fingerprint"])
print("→ 逻辑改了、读数从 1.0 变 0.0，指纹却一字未变 ⇒ ‘改尺子仍报同一指纹’没被堵住")
M._rate = orig

# ---------------------------------------------------------------- P4
line("P4  未知/拼错的 relation 会怎样？会不会出声？")
p = {**base, "entries": [{"entry": "A", "intent": "x", "items": [
    {"relation": "independent"}, {"relation": "independant"},   # 拼错
    {"relation": "Independent"}]}]}                             # 大小写错
r = M.compute(p)
print("overall =", r["openness_overall"], " expected(若都认作独立) = 1.0")
print("flags   =", r["flags"])
print("→ 拼错被静默当成‘不开放’，把开放度往下压，且无任何数据质量告警")

# ---------------------------------------------------------------- P5
line("P5  CLI 参数名与 README 是否对得上？")
import argparse
print("README 写:  python measure.py --input selftest_fixture.json --output readings.json")
print("代码实际:  --in / --out")
try:
    M.main.__wrapped__ if hasattr(M.main, "__wrapped__") else None
except Exception:
    pass
import subprocess, sys
out = subprocess.run([sys.executable, "measure_v20.py", "--input", "x.json"],
                     capture_output=True, text=True)
print("实跑 `--input x.json` 的返回码 =", out.returncode)
print((out.stdout + out.stderr).strip().splitlines()[-1] if (out.stdout + out.stderr).strip() else "")

# ---------------------------------------------------------------- P6
line("P6  compare() 会不会把‘入口方自证’的读数当独立读数来比对？")
a = {**base, "independence": "provided_by_entry",
     "entries": [{"entry": "E", "intent": "i", "items": [{"relation": "independent"}] * 2}]}
b = {**base, "entries": [{"entry": "E", "intent": "i", "items": [{"relation": "independent"}] * 2}]}
json.dump(M.compute(a), open("p6a.json", "w", encoding="utf-8"), ensure_ascii=False)
json.dump(M.compute(b), open("p6b.json", "w", encoding="utf-8"), ensure_ascii=False)
print(json.dumps(M.compare("p6a.json", "p6b.json"), ensure_ascii=False, indent=2))
print("→ 没有对 independence 做任何拦截，自证数据照样进‘一致性’结论")

# ---------------------------------------------------------------- P7
line("P7  全部空样本的入口，在 per_entry / spread 里会消失吗？")
p = {**base, "entries": [
    {"entry": "有数据", "intent": "i", "items": [{"relation": "independent"}] * 2},
    {"entry": "全空",   "intent": "i", "items": []}]}
r = M.compute(p)
print("per_entry =", r["per_entry_openness"], " spread =", r["spread"], " uncomputable =", r["uncomputable"])
print("→ ‘全空’入口从 per_entry 里消失，读者看不到它‘没测到’")

# ---------------------------------------------------------------- P8
line("P8  relation 词表有没有校验收口？（协议只列了 7 类）")
KNOWN = {"independent", "marked_paid", "suspected_paid", "self", "affiliate", "equity", "exclusive"}
print("代码里被显式识别的只有: suspected_paid / marked_paid / self/affiliate/equity/exclusive / independent")
print("其余一律静默落入‘非开放’：无白名单校验、无非空校验、无 id 去重")
print("KNOWN(7类) =", sorted(KNOWN))

# ---------------------------------------------------------------- P9
line("P9  CLI 读文件处异常处理：坏 JSON / 文件不存在会怎样？")
out = subprocess.run([sys.executable, "measure_v20.py", "--in", "不存在.json"],
                     capture_output=True, text=True)
tail = (out.stdout + out.stderr).strip().splitlines()
print("返回码 =", out.returncode)
print("末行   =", tail[-1] if tail else "")
print("→ 直接抛裸 traceback，无友好报错（工程瑕疵，非口径问题）")

# ---------------------------------------------------------------- P10
line("P10  reading_fingerprint 的基里含 independence 吗？")
p_no = {**base, "entries": [{"entry": "E", "intent": "i", "items": [{"relation": "independent"}] * 2}]}
r1 = M.compute(p_no)
r2 = M.compute({**p_no, "independence": "has_relation"})
print("none           reading_fingerprint =", r1["reading_fingerprint"], " overall =", r1["openness_overall"])
print("has_relation   reading_fingerprint =", r2["reading_fingerprint"], " overall =", r2["openness_overall"])
print("→ 两枚指纹相同：效力状态不进读数指纹，同一读数‘可用/参考’共用一枚指纹")

print("\n" + "=" * 62)
print("探测结束。")
