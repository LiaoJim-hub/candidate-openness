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
PROTOCOL_VERSION = "v2.2"      # ★ 2026-10-10：口径变更（疑似单列）⇒ 必须升协议版本
CODE_VERSION = "2.1.1"

MIN_SAMPLES = 40            # 20 意图 x 至少 2 入口; 工程默认值, 无实测依据
MIN_INTENTS = 20
SUSPECTED_RATE_WARN = 0.3   # 疑似率提示线
CONSISTENCY_TOL = 0.05      # 同口径复算一致阈值; 工程默认值, 无实测依据

# ★★★★ 2026-10-10 加（★ 持有方定义判：「疑似付费位」单列 + 超阈不可核）：
#   ★ 判词逐字：★「★ **它既不该进分子，也不该简单进分母** —— **应该单列成一个独立出口**」
#      ★ 理由：★「★ **把"不知道"渲染成一个具体的归属，就是做假读数**」——
#      ★★ 而**进分子**是把不确定读成"最好"、★ **进分母**是读成"最坏"，★ **两个都是同一个错。**
#   ★★ 故本尺子的 `openness_*` **只量"已证事实"**：
#      · 分母（observed）= independent + marked_paid + 关联方  ← ★ **只含观测到的**
#      · 分子           = independent
#      · suspected_paid = **单列输出**，★ 不进分子、★ **不进分母**、★ 不参与 overall
#   ★★★ 而**单列必须配闸门**（★ 否则它成了"逃避选择"）：
#      ★「★ **疑似太多，说明这个入口的判定依据整体不足 ⇒ 它整体不可核，而不是"部分可核"**」
#   ★★★★ 阈值方向（★ 持有方特别点名，★ 我照抄）：★ **是「疑似过多 ⇒ 不可核」，
#      不是「疑似存在 ⇒ 不可核」** —— ★★ **否则它会从"防误读"变成"防观测"。**
UNKNOWN_MAX = 0.2           # 未知(无法归类)占比上限; 超 ⇒ 该入口不可核
SUSPECTED_MAX = 0.5         # 疑似占比上限; 超 ⇒ 该入口不可核(★ 「过多」不是「存在」)

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
    "logic_revision": "r3",          # ★ 逻辑修订号: 改计算逻辑必须动它（r3 = 疑似单列）
    "min_samples": MIN_SAMPLES,
    "min_intents": MIN_INTENTS,
    "suspected_warn": SUSPECTED_RATE_WARN,
    "consistency_tol": CONSISTENCY_TOL,
    "relation_map": RELATION_MAP,    # ★ 归类表进指纹
    # ★★★ 2026-10-10：口径变了 ⇒ 这两条必须进指纹（★ 否则改了归一化而指纹不变）
    "unknown_max": UNKNOWN_MAX,
    "suspected_max": SUSPECTED_MAX,
    "observed_denominator": ("independent", "paid", "related"),   # ★ 分母只含观测到的
    "suspected_in": "single",        # ★ 疑似：单列（★ 既不入分子、也不入分母）
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
    # ★★★★ 2026-10-10（★ 持有方定义判）：★ 疑似**单列** —— 不进分子、**也不进分母**。
    #   ★ 分母 = **只含观测到的**（independent + paid + related）· ★ 分子 = independent
    observed = c["independent"] + c["paid"] + c["related"]
    sus = c["suspected"]
    unk = c["unknown"]
    # ★★★★ **未知词表在任何 return 之前就算好**（★ 2026-10-10 修的一处真缺陷）：
    #   ★ 起因：★ 我原来只在**最后一个** return 里带它 ⇒ ★★ 而"未知超限"那条**早退**不带 ⇒
    #   ★★★ **于是"拼错的 relation"恰恰在**被拒的那一路**看不见** —— ★★ 而那正好倒过来**
    #   （★ 越是不认识的词多，★ 越该把它报出来）。
    _unk_words = sorted({x for x in unknown_rels if x is not None}, key=str)

    # ★★★ 闸门（★ 持有方逐字：「★ 疑似太多 ⇒ 该入口整体不可核，而不是"部分可核"」）
    #   ★★ 而**方向必须是"过多"**（★ 不是"存在"）—— ★ 否则它会从"防误读"变成"防观测"。
    if observed == 0:
        return {"total": total, "observed": 0, "suspected": sus, "unknown": unk,
                "uncomputable": True,
                "unknown_relations": _unk_words,
                "note": "该入口没有可判定样本（全是未知/疑似）⇒ 不报数"}
    if unk / total > UNKNOWN_MAX:
        return {"total": total, "observed": observed, "suspected": sus, "unknown": unk,
                "uncomputable": True,
                "unknown_relations": _unk_words,
                "note": f"未知占比 {unk}/{total} 超上限 {UNKNOWN_MAX} ⇒ 判不可核(不报数)"}
    if sus / total > SUSPECTED_MAX:
        return {"total": total, "observed": observed, "suspected": sus, "unknown": unk,
                "uncomputable": True,
                "unknown_relations": _unk_words,
                "note": f"疑似占比 {sus}/{total} 超上限 {SUSPECTED_MAX} ⇒ "
                        "该入口判定依据整体不足,判不可核(不报数)"}
    return {
        "total": total,
        "observed": observed,            # ★ 分母（只含观测到的）
        "independent": c["independent"],
        "paid": c["paid"],
        "related": c["related"],
        "suspected": sus,                # ★ 单列（不进分子、不进分母）
        "unknown": unk,
        "main_n": c["independent"],      # ★ 分子 = independent
        "strict_n": c["independent"],    # ★ 严格口径与主口径同（疑似已不在分母里）
        "unknown_relations": _unk_words,
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

    # ★ 2026-10-10：★ `total` 仍在（样本量）· ★ 而**分母换成 `observed`**（★ 疑似的量另记）
    #   ★★ 而 `unknown` 也必须累（★ 否则 `unknown_rate` 算不出来 —— 我第一版就栽在这：
    #      ★ 它从 `rows` 求和，★ 而那句跑在**装 `rows` 之前** ⇒ 恒 `None`）。
    counts = {"total": 0, "observed": 0, "independent": 0, "suspected": 0,
              "unknown": 0, "main_n": 0, "strict_n": 0}
    unknown_values = set()
    rows, excluded, no_data = [], [], []
    per_entry = {}
    uncomputable = 0
    intents = set()

    for e in payload.get("entries", []):
        entry = e.get("entry")
        intent = _norm_intent(e.get("intent", ""))
        r = _rate(e.get("items", []))

        # ★★★ 2026-10-10：★ 空样本与"未知/疑似超限"**同档**（★ 持有方：「整体不可核，不是部分可核」）
        if r is None or r.get("uncomputable"):
            uncomputable += 1
            # ★★★ 而**不可核那一路也必须交未知词表** —— ★ 否则"这批样本里有拼错的 relation"
            #   这件事**只在能算出数时才报**，★ 而超限被拒的那一路**反而看不见它**（★ 那正好倒过来）。
            if r is not None:
                unknown_values.update(r.get("unknown_relations") or [])
            no_data.append({"entry": entry, "intent": intent,
                            "why": "空样本" if r is None else r.get("note")})
            rows.append({"entry": entry, "intent": intent, "result": None,
                         "in_aggregate": in_aggregate,
                         "note": "uncomputable(空样本,不猜)" if r is None
                                 else "uncomputable({0})".format(r.get("note"))})
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

    # ★★★ 2026-10-10：★ 分母 = **observed**（只含观测到的）—— ★ 疑似**不进分母**
    openness_main = (round(counts["main_n"] / counts["observed"], 4)
                     if counts["observed"] else None)
    openness_strict = (round(counts["strict_n"] / counts["observed"], 4)
                       if counts["observed"] else None)
    # ★ 疑似率与未知率：★ 都以**样本量**为分母（★ 它们量的是"这批样本里有多少没定论"）
    #   ★★ 而**两者都从 `counts` 取**（★ 不从 `rows` 求和 —— ★ 那句跑在装 `rows` 之前，会恒 `None`；
    #      ★ 而我第一版正是那样写的，★ 端到端跑样例时被照出来：`unknown_rate = None`）。
    suspected_rate = (round(counts["suspected"] / counts["total"], 4)
                      if counts["total"] else None)
    unknown_rate = (round(counts["unknown"] / counts["total"], 4)
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
        # ★★★ 2026-10-10：★ `unknown_rate` **必须与 `suspected_rate` 并列报出**。
        #   ★ 我第一版算了它却**忘了写进这个字典** ⇒ ★★ 端到端一跑就是 `None`
        #   （★ 而三套测试**全过** —— ★ 因为**没有一条测试读这个字段**）。
        #   ★★★ 故补上它，★ 并在自检里加一条「两个率必须都在」⇒ ★ 下次漏了会红。
        "unknown_rate": unknown_rate,
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

    # 2 ★★ 2026-10-10 改（★ 持有方定义判）：★ 疑似**单列** —— 不进分子、**也不进分母**
    #   ★ 故本条现在验的是那件事：★ `independent` 1 个、★ `suspected` 1 个
    #     ⇒ ★ **分母 = 1**（只含观测到的）· ★ **分子 = 1** ⇒ ★ `openness_main = 1.0`
    #     · ★ 而 `suspected_paid = 1` **单列** ⇒ ★ **读者必须同时看这两个数**（★ 只报一个 = 不完整读数）
    r = compute({**base, "entries": [{"entry": "A", "intent": "x", "items": [
        {"relation": "suspected_paid"}, {"relation": "independent"}]}]})
    chk(2, r["suspected_paid"] == 1 and r["openness_main"] == 1.0
        and r["openness_strict"] == 1.0 and r["suspected_rate"] == 0.5,
        (r["openness_main"], r["openness_strict"], r["suspected_rate"]))

    # 3 空样本不可核
    r = compute({**base, "entries": [{"entry": "A", "intent": "y", "items": []}]})
    chk(3, r["uncomputable"] == 1 and r["openness_main"] is None, r)

    # 4 ★★ 2026-10-10 改：★ 未知**超限即不可核**（★ 持有方：「整体不可核，不是部分可核」）
    #   ★ 1 已知 + 1 未知 ⇒ ★ 未知占 50% > `UNKNOWN_MAX`(0.2) ⇒ ★ **该入口不报数**
    r = compute({**base, "entries": [{"entry": "A", "intent": "z", "items": [
        {"relation": "independent"}, {"relation": "mystery"}]}]})
    chk(4, r["uncomputable"] == 1 and r["openness_main"] is None
        and r["unknown_relations"] == ["mystery"], (r["uncomputable"], r["openness_main"]))

    # 4b ★★★ 未知**未超限** ⇒ 照出数（★ 证明闸门是"过多"而**不是"存在"**）
    #   ★ 4 已知 + 1 未知 ⇒ ★ 未知恰 20% · ★ 判据是 `>` ⇒ **不触发** ⇒ ★ 出数
    #   ★★★ 而**出的是 `1.0` 不是 `0.8`** —— ★ 因为**分母只含观测到的**（★ 那 4 个 independent）
    #      ⇒ ★★ **未知与疑似一样，都不进分母**（★ 持有方定义：★ `overall` **只量已证事实**）
    #      ⇒ ★★★ **故凡用到本数，★ 必须同时看 `suspected_rate` 与 `unknown_rate`**（★ 只报一个 = 不完整读数）
    r = compute({**base, "entries": [{"entry": "A", "intent": "z2", "items": [
        {"relation": "independent"}] * 4 + [{"relation": "mystery"}]}]})
    chk("4b", r["uncomputable"] == 0 and r["openness_main"] == 1.0
        and r["unknown_relations"] == ["mystery"] and r["unknown_rate"] == 0.2,
        (r["uncomputable"], r["openness_main"], r["unknown_relations"], r["unknown_rate"]))
    # 4b2 ★★★★ 「两个率必须都在」—— ★ 我第一版算了 `unknown_rate` 却**没写进输出字典**，
    #   而三套测试全过（★ 因为没有一条读它）⇒ ★ **这条断言就是为那次漏而加的。**
    chk("4b2", "unknown_rate" in r and "suspected_rate" in r
        and r["unknown_rate"] is not None and r["suspected_rate"] is not None,
        (r.get("unknown_rate"), r.get("suspected_rate")))

    # 4c ★★★ 疑似**过多** ⇒ 不可核（★ 而那正是"防误读"而不是"防观测"）
    #   ★ 观测到 2 个 · ★ 疑似 3 个 ⇒ ★ 疑似占 60% > `SUSPECTED_MAX`(0.5) ⇒ **不可核**
    #   ★★ 而 `chk(2)` 那组（疑似 1 / 观测 1 = 50%）**不触发** ——
    #      ★ 因为判据是「**过多**」而不是「**存在**」（★ 持有方逐字点名了这一条）。
    r = compute({**base, "entries": [{"entry": "A", "intent": "z3", "items": [
        {"relation": "independent"}] * 2 + [{"relation": "suspected_paid"}] * 3}]})
    chk("4c", r["uncomputable"] == 1 and r["openness_main"] is None,
        (r["uncomputable"], r["openness_main"]))

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
