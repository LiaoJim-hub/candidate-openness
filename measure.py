#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
候选集开放度 · 尺子  (Candidate Openness)
协议口径: v2.1    ·    代码版本: 2.1.1

一句话: 量"同一个购买意图下, 入口直接给出的候选中, 非付费位、非关联方的占比"。

v2.1 相对 v2.0 的变更 (实现层修订, 详见 CHANGELOG.md 与 docs/代码审核报告.md):
  A1  修复 provided_by_entry 未排除聚合         —— 与 PROTOCOL §8 声明一致
  A2  口径指纹纳入 relation 归类表 + 逻辑修订号  —— 改逻辑 => 指纹必变
  A3  读数指纹纳入分布(spread/per_entry)         —— 杜绝"两极 = 均匀"撞车
  A4  并列报出主口径 openness_main 与严格口径 openness_strict
  A5  compare() 拒绝把非独立读数当作一致性依据
  A6  relation 词表白名单校验, 未知值单列告警
  A7  无数据入口显式登记, 不再从 per_entry 静默消失
  A8  CLI 同时接受 --in/--out 与 --input/--output
  A9  效力状态纳入读数指纹
  A10 读文件友好报错
"""
import argparse
import copy
import hashlib
import json
import sys
from datetime import datetime, timezone

# ----------------------------------------------------------------------
# 常量  (★ 凡进入 CALIBER 的, 改它就等于改口径, 必须升协议版本)
# ----------------------------------------------------------------------
PROTOCOL_VERSION = "v2.1"
CODE_VERSION = "2.1.1"

MIN_SAMPLES = 40            # 20 意图 x 至少 2 入口; 工程默认值, 无实测依据
MIN_INTENTS = 20
SUSPECTED_RATE_WARN = 0.3   # 疑似率提示线
CONSISTENCY_TOL = 0.05      # 同口径复算一致阈值; 工程默认值, 无实测依据

# relation -> 归类。★ 这张表参与口径指纹。
RELATION_MAP = {
    "independent": "independent",   # 中立候选
    "marked_paid": "paid",          # 入口自身标注的付费位
    "suspected_paid": "suspected",  # 无标注但具备可外部复核的推广特征
    "self": "related",              # 自家
    "affiliate": "related",         # 返佣/联盟
    "equity": "related",            # 股权关联
    "exclusive": "related",         # 独家/排他
}
CATEGORIES = ("independent", "paid", "related", "suspected", "unknown")

INDEPENDENCE_MODES = ("none", "has_relation", "provided_by_entry")
EFFECT_TEXT = {
    "none": "读数可用",
    "has_relation": "参考(测量者与入口方有关系)",
    "provided_by_entry": "不算独立读数",
}

# ★ compare 的完整性必报项 (PROTOCOL §5 报数纪律)。缺任一 ⇒ 判不完整,不得引用。
REQUIRED_FIELDS = ("openness_main", "openness_strict", "per_entry_openness",
                   "spread", "samples", "intents", "suspected_rate",
                   "caliber_fingerprint")

CALIBER = {
    "protocol_version": PROTOCOL_VERSION,
    "logic_revision": "r2",          # ★ 逻辑修订号: 改计算逻辑必须动它
    "min_samples": MIN_SAMPLES,
    "min_intents": MIN_INTENTS,
    "suspected_warn": SUSPECTED_RATE_WARN,
    "consistency_tol": CONSISTENCY_TOL,
    "relation_map": RELATION_MAP,    # ★ 归类表进指纹
}


# ----------------------------------------------------------------------
# 口径指纹
# ----------------------------------------------------------------------
def _caliber_fingerprint(caliber=None) -> str:
    basis = json.dumps(caliber if caliber is not None else CALIBER,
                       sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


def _norm_intent(s: str) -> str:
    return " ".join((s or "").split()).strip()


# ----------------------------------------------------------------------
# 单入口样本计算
# ----------------------------------------------------------------------
def _rate(items):
    """返回单入口样本的分类计数; 空样本返回 None(不猜)。"""
    total = len(items)
    if total == 0:
        return None
    c = {k: 0 for k in CATEGORIES}
    unknown_rels = []
    for it in items:
        rel = it.get("relation")
        cat = RELATION_MAP.get(rel, "unknown")
        c[cat] += 1
        if cat == "unknown":
            unknown_rels.append(rel)
    return {
        "total": total,
        "independent": c["independent"],
        "paid": c["paid"],
        "related": c["related"],
        "suspected": c["suspected"],
        "unknown": c["unknown"],
        # 主口径: 既非付费标注位, 也非关联方 (疑似计入分子)
        "main_n": c["independent"] + c["suspected"],
        # 严格口径: 再扣除疑似
        "strict_n": c["independent"],
        "unknown_relations": sorted({x for x in unknown_rels if x is not None},
                                    key=str),
    }


# ----------------------------------------------------------------------
# 主计算
# ----------------------------------------------------------------------
def compute(payload):
    indep = payload.get("independence", "none")
    if indep not in INDEPENDENCE_MODES:
        indep = "none"
    effect = EFFECT_TEXT[indep]
    # ★ 只有 provided_by_entry 才被排除聚合; has_relation 是"可用但降级为参考"。
    in_aggregate = not (indep == "provided_by_entry")
    independent_reading = (indep == "none")
    # ★ 自证数据必须显式标出(闸门位, 不是影子)
    suppressed = (indep == "provided_by_entry")

    counts = {"total": 0, "independent": 0, "suspected": 0, "main_n": 0, "strict_n": 0}
    unknown_values = set()
    rows, excluded, no_data = [], [], []
    per_entry = {}
    uncomputable = 0
    intents = set()

    for e in payload.get("entries", []):
        entry = e.get("entry")
        intent = _norm_intent(e.get("intent", ""))
        r = _rate(e.get("items", []))

        if r is None:
            uncomputable += 1
            no_data.append({"entry": entry, "intent": intent})
            rows.append({"entry": entry, "intent": intent, "result": None,
                         "in_aggregate": in_aggregate,
                         "note": "uncomputable(空样本,不猜)"})
            continue

        intents.add(intent)
        row = {"entry": entry, "intent": intent,
               "in_aggregate": in_aggregate, "result": r}

        if not in_aggregate:
            row["note"] = f"排除聚合(效力:{effect})"
            excluded.append({"entry": entry, "intent": intent, "result": r})
            rows.append(row)
            continue

        for k in counts:
            counts[k] += r[k]
        unknown_values.update(r["unknown_relations"])
        rows.append(row)
        a = per_entry.setdefault(entry, {"n": 0, "main": 0, "strict": 0})
        a["n"] += r["total"]
        a["main"] += r["main_n"]
        a["strict"] += r["strict_n"]

    per_entry_main = {k: round(v["main"] / v["n"], 4)
                      for k, v in per_entry.items() if v["n"]}
    per_entry_strict = {k: round(v["strict"] / v["n"], 4)
                        for k, v in per_entry.items() if v["n"]}
    spread = (round(max(per_entry_main.values()) - min(per_entry_main.values()), 4)
              if len(per_entry_main) >= 2 else None)

    openness_main = (round(counts["main_n"] / counts["total"], 4)
                     if counts["total"] else None)
    openness_strict = (round(counts["strict_n"] / counts["total"], 4)
                       if counts["total"] else None)
    suspected_rate = (round(counts["suspected"] / counts["total"], 4)
                      if counts["total"] else None)

    flags = []
    if counts["total"] < MIN_SAMPLES:
        flags.append(f"样本不足(<{MIN_SAMPLES}),读数统计意义弱")
    if intents and len(intents) < MIN_INTENTS:
        flags.append(f"意图数不足(<{MIN_INTENTS})")
    if suspected_rate is not None and suspected_rate > SUSPECTED_RATE_WARN:
        flags.append("疑似付费位占比偏高,请复核 relation 判定")
    if unknown_values:
        flags.append(f"存在未识别 relation 值 {sorted(unknown_values, key=str)},"
                     "已按非开放保守计入,请核对词表")
    if no_data:
        flags.append(f"{len(no_data)} 个入口无可用样本,未计入 per_entry")
    if not in_aggregate:
        flags.append(f"独立性:{effect} —— 该读数不参与聚合")
    elif not independent_reading:
        flags.append(f"独立性:{effect} —— 该读数仅供参考,不得单独对外引用")

    caliber_fp = _caliber_fingerprint()
    result = {
        "protocol_version": PROTOCOL_VERSION,
        "code_version": CODE_VERSION,
        "caliber_fingerprint": caliber_fp,
        "taken_at": payload.get("taken_at"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "independence": indep,
        "effect": effect,
        "suppressed": suppressed,
        # —— 头条指标: 主口径 (README 定义)。overall 为向后兼容别名, 与 main 同值。
        "openness_main": openness_main,
        "openness_overall": openness_main,
        "openness_strict": openness_strict,
        "per_entry_openness": per_entry_main,
        "per_entry_openness_strict": per_entry_strict,
        "spread": spread,
        "samples": counts["total"],
        "intents": len(intents),
        "suspected_paid": counts["suspected"],
        "suspected_rate": suspected_rate,
        "unknown_relations": sorted(unknown_values, key=str),
        "uncomputable": uncomputable,
        "entries_without_data": no_data,
        "excluded_from_aggregate": excluded,
        "flags": flags,
        "detail": rows,
    }

    # 读数指纹: 口径 + 头条读数 + 分布 + 样本量 + 效力 (★ 分布与效力一并进指纹)
    basis = json.dumps({
        "caliber": caliber_fp,
        "openness_main": openness_main,
        "openness_strict": openness_strict,
        "spread": spread,
        "per_entry": per_entry_main,
        "samples": counts["total"],
        "intents": len(intents),
        "independence": indep,
    }, sort_keys=True, ensure_ascii=False)
    result["reading_fingerprint"] = hashlib.sha256(
        basis.encode("utf-8")).hexdigest()[:16]
    return result


# ----------------------------------------------------------------------
# 同口径复算比对
# ----------------------------------------------------------------------
def _load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise SystemExit(f"[错误] 找不到文件: {path}")
    except json.JSONDecodeError as ex:
        raise SystemExit(f"[错误] JSON 解析失败: {path} ({ex})")


def compare(a_path, b_path):
    """同口径独立复算比对 (只接受完整、独立的读数)。

    ★ 完整性按 PROTOCOL §5 报数纪律执行: 必报项一个都不许缺。
      单入口读数 spread 为 None ⇒ 判为不完整, 不得比对 (不再豁免)。
    """
    a, b = _load(a_path), _load(b_path)
    if a.get("caliber_fingerprint") != b.get("caliber_fingerprint"):
        return {"comparable": False,
                "reason": "口径指纹不同,不可比对(请先统一口径)"}
    for name, r in (("a", a), ("b", b)):
        if r.get("suppressed"):
            return {"comparable": False,
                    "reason": f"读数 {name} 为自证数据(不出数),不是独立读数,不可比对"}
        if r.get("independence", "none") != "none":
            return {"comparable": False,
                    "reason": f"读数 {name} 效力为「{r.get('effect')}」,"
                              "不是独立读数,不作一致性比对"}
        missing = [f for f in REQUIRED_FIELDS if r.get(f) is None]
        if missing:
            return {"comparable": False,
                    "reason": f"读数 {name} 不完整(缺 {missing}),不得引用"}
    out = {
        "comparable": True,
        "a_main": a.get("openness_main"), "b_main": b.get("openness_main"),
        "a_strict": a.get("openness_strict"), "b_strict": b.get("openness_strict"),
        "a_spread": a.get("spread"), "b_spread": b.get("spread"),
        "a_per_entry": a.get("per_entry_openness"),
        "b_per_entry": b.get("per_entry_openness"),
        "a_fingerprint": a.get("reading_fingerprint"),
        "b_fingerprint": b.get("reading_fingerprint"),
    }
    am, bm = a.get("openness_main"), b.get("openness_main")
    if am is None or bm is None:
        out["note"] = "有一侧不可核,不作一致性判断"
    else:
        d = abs(am - bm)
        out["abs_diff_main"] = round(d, 4)
        out["consistent"] = d <= CONSISTENCY_TOL
    return out


# ----------------------------------------------------------------------
# 自检
# ----------------------------------------------------------------------
def _selftest():
    ok = True

    def chk(n, cond, got=None):
        nonlocal ok
        if not cond:
            print(f"FAIL {n}:", got)
            ok = False

    base = {"taken_at": "2026-10-10T00:00:00Z"}

    # 1 基本占比 (无疑似 -> 主/严格同值)
    r = compute({**base, "entries": [{"entry": "A", "intent": "通勤鞋", "items": [
        {"relation": "independent"}, {"relation": "marked_paid"},
        {"relation": "affiliate"}, {"relation": "independent"}]}]})
    chk(1, r["openness_main"] == 0.5 and r["openness_strict"] == 0.5, r["openness_main"])

    # 2 ★ 主/严格并列: 疑似计入主口径分子, 不进严格口径
    r = compute({**base, "entries": [{"entry": "A", "intent": "x", "items": [
        {"relation": "suspected_paid"}, {"relation": "independent"}]}]})
    chk(2, r["suspected_paid"] == 1 and r["openness_main"] == 1.0
        and r["openness_strict"] == 0.5, (r["openness_main"], r["openness_strict"]))

    # 3 空样本不可核
    r = compute({**base, "entries": [{"entry": "A", "intent": "y", "items": []}]})
    chk(3, r["uncomputable"] == 1 and r["openness_main"] is None, r)

    # 4 ★ 未知 relation 保守 + 告警
    r = compute({**base, "entries": [{"entry": "A", "intent": "z", "items": [
        {"relation": "independent"}, {"relation": "mystery"}]}]})
    chk(4, r["openness_main"] == 0.5 and r["unknown_relations"] == ["mystery"]
        and any("未识别" in f for f in r["flags"]), r["flags"])

    # 5 ★ 分布: 两极 vs 均匀
    r = compute({**base, "entries": [
        {"entry": "P", "intent": "i1", "items": [{"relation": "independent"}] * 2},
        {"entry": "Q", "intent": "i1", "items": [{"relation": "marked_paid"}] * 2}]})
    chk(5, r["openness_main"] == 0.5 and r["spread"] == 1.0,
        (r["openness_main"], r["spread"]))

    # 6 ★ 自证拒收: 标签 + 真不聚合
    r = compute({**base, "independence": "provided_by_entry",
                 "entries": [{"entry": "A", "intent": "i", "items": [
                     {"relation": "independent"}]}]})
    chk(6, r["effect"] == "不算独立读数" and r["openness_main"] is None
        and len(r["excluded_from_aggregate"]) == 1
        and any("不参与聚合" in f for f in r["flags"]), r["flags"])

    # 7 口径指纹在位
    chk(7, len(compute({**base, "entries": []})["caliber_fingerprint"]) == 16)

    # 8 样本不足提示
    r = compute({**base, "entries": [{"entry": "A", "intent": "i", "items": [
        {"relation": "independent"}]}]})
    chk(8, any("样本不足" in f for f in r["flags"]), r["flags"])

    # 9 ★ 改归类表 => 口径指纹必变
    c2 = copy.deepcopy(CALIBER)
    c2["relation_map"]["independent"] = "related"
    chk(9, _caliber_fingerprint(c2) != _caliber_fingerprint(CALIBER),
        _caliber_fingerprint(CALIBER))

    # 10 ★ 结构相反(均匀/两极)、总占比相同 => 读数指纹必须不同
    uniform = {**base, "entries": [
        {"entry": k, "intent": "i", "items":
            [{"relation": "independent"}, {"relation": "marked_paid"}]}
        for k in ("A", "B", "C", "D")]}
    polar = {**base, "entries": [
        {"entry": "P", "intent": "i", "items": [{"relation": "independent"}] * 4},
        {"entry": "Q", "intent": "i", "items": [{"relation": "marked_paid"}] * 4}]}
    ru, rp = compute(uniform), compute(polar)
    chk(10, ru["openness_main"] == rp["openness_main"]
        and ru["reading_fingerprint"] != rp["reading_fingerprint"],
        (ru["reading_fingerprint"], rp["reading_fingerprint"]))

    # 11 ★ 效力状态进读数指纹
    p = {**base, "entries": [{"entry": "A", "intent": "i",
                              "items": [{"relation": "independent"}] * 2}]}
    r_none = compute(p)
    r_rel = compute({**p, "independence": "has_relation"})
    chk(11, r_none["reading_fingerprint"] != r_rel["reading_fingerprint"],
        (r_none["reading_fingerprint"], r_rel["reading_fingerprint"]))

    # 12 ★ 无数据入口被登记
    r = compute({**base, "entries": [
        {"entry": "有数据", "intent": "i", "items": [{"relation": "independent"}] * 2},
        {"entry": "全空", "intent": "i", "items": []}]})
    chk(12, r["entries_without_data"] and any("无可用样本" in f for f in r["flags"]), r)

    print("SELFTEST", PROTOCOL_VERSION, ":", "PASS" if ok else "FAIL")
    return 0 if ok else 1


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        description=f"候选集开放度尺子 (protocol {PROTOCOL_VERSION})")
    ap.add_argument("--version", action="version",
                    version=f"%(prog)s {CODE_VERSION} (protocol {PROTOCOL_VERSION})")
    ap.add_argument("--selftest", action="store_true", help="跑内置自检")
    ap.add_argument("--in", "--input", dest="infile", metavar="PAYLOAD.json",
                    help="输入 payload")
    ap.add_argument("--out", "--output", dest="outfile", metavar="READING.json",
                    help="输出读数 JSON")
    ap.add_argument("--compare", nargs=2, metavar=("A.json", "B.json"),
                    help="同口径独立复算比对")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()
    if args.compare:
        print(json.dumps(compare(*args.compare), ensure_ascii=False, indent=2))
        return 0
    if not args.infile:
        ap.print_help()
        return 2

    payload = _load(args.infile)
    res = json.dumps(compute(payload), ensure_ascii=False, indent=2)
    if args.outfile:
        with open(args.outfile, "w", encoding="utf-8") as f:
            f.write(res)
        print("written:", args.outfile)
    else:
        print(res)
    return 0


if __name__ == "__main__":
    sys.exit(main())
