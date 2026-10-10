# -*- coding: utf-8 -*-
"""P11：‘两极’与‘均匀’两种结构完全相反的读数，指纹是否相同？"""
import measure_v20 as M
base = {"taken_at": "2026-10-10T00:00:00Z"}

# 均匀：四个入口各 0.5
uniform = {**base, "entries": [
    {"entry": "A", "intent": "i", "items": [{"relation": "independent"}, {"relation": "marked_paid"}]},
    {"entry": "B", "intent": "i", "items": [{"relation": "independent"}, {"relation": "marked_paid"}]},
    {"entry": "C", "intent": "i", "items": [{"relation": "independent"}, {"relation": "marked_paid"}]},
    {"entry": "D", "intent": "i", "items": [{"relation": "independent"}, {"relation": "marked_paid"}]},
]}
# 两极：P 全开放、Q 全付费（overall 同为 0.5, samples 同为 8? 需要样本数一致）
polar = {**base, "entries": [
    {"entry": "P", "intent": "i", "items": [{"relation": "independent"}] * 4},
    {"entry": "Q", "intent": "i", "items": [{"relation": "marked_paid"}] * 4},
]}
ru, rp = M.compute(uniform), M.compute(polar)
print("均匀  overall=%.4f samples=%d spread=%s reading_fp=%s"
      % (ru["openness_overall"], ru["samples"], ru["spread"], ru["reading_fingerprint"]))
print("两极  overall=%.4f samples=%d spread=%s reading_fp=%s"
      % (rp["openness_overall"], rp["samples"], rp["spread"], rp["reading_fingerprint"]))
print("两枚 reading_fingerprint 是否相同：", ru["reading_fingerprint"] == rp["reading_fingerprint"])
print("→ 结构完全相反（均匀 vs 两极），总占比与样本数相同 ⇒ 读数指纹撞车；"
      "v2.0 升级一强调的‘分布’没有进指纹，比对时会被判为‘一致’。")

# 反向：compare 只比 overall，不看 spread
import json
json.dump(ru, open("u.json", "w", encoding="utf-8"), ensure_ascii=False)
json.dump(rp, open("p.json", "w", encoding="utf-8"), ensure_ascii=False)
print("\ncompare(均匀, 两极) =", json.dumps(M.compare("u.json", "p.json"), ensure_ascii=False))
