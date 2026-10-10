# CHANGELOG

本文件记录**协议口径**与**代码**的变更。口径变更必须升协议版本（口径指纹随之改变）。

---

## v2.1 — 2026-10-10 · 代码审核修订

来源：`docs/代码审核报告.md`（对 v2.0 代码的 11 项审核发现）。
本版**不改变"开放度"的定义**，只让实现与 PROTOCOL 对齐、堵住误用口。

### 修复
- **A1** `provided_by_entry` 的条目**真正排除**出 `openness_*` / `per_entry` /
  `spread` / 全部计数，登记于 `excluded_from_aggregate`（对齐 PROTOCOL §6）。
- **A2** 口径指纹纳入 **relation 归类表** 与 `logic_revision`；改逻辑 ⇒ 指纹必变。
- **A3** 读数指纹纳入 **`spread` 与 `per_entry`**；"均匀 vs 两极"不再撞车。
- **A4** 并列报出 **`openness_main`（主口径）** 与 **`openness_strict`（严格口径）**；
  `openness_overall` 保留为 `openness_main` 的向后兼容别名。
- **A5** `compare()` 先验效力，非独立读数（`has_relation` / `provided_by_entry`）**拒绝比对**。
- **A6** relation **白名单校验**，未知值归 `unknown` 保守计入并告警（`unknown_relations`）。
- **A7** 无可用样本的入口登记于 **`entries_without_data`** 并告警。
- **A8** CLI 同时接受 `--in/--out` 与 `--input/--output`。
- **A9** 效力状态 `independence` 纳入读数指纹。
- **A10** 读文件友好报错（`[错误] 找不到文件 / JSON 解析失败`）。
- **A11** 删除 `_rate` 的死字段；新增 `--version`。

### 新增
- `tests/test_measure.py`（unittest 套件）。
- 自检由 8 条扩到 **12 条**，新增第 9/10/11/12 条针对上述修复的**反向断言**。
- `docs/代码审核报告.md`。

### ⚠️ 语义决定（需作者确认）
`openness_overall` 由 v2.0 的**严格口径**恢复为 README 字面定义的**主口径**。
若你本意是严格口径当头条，改 `measure.py` 若干行并升版本即可，见审核报告 §二。

---

## v2.0 — 2026-10-10 · 协议升级

- 报**分布**（`per_entry_openness` / `spread`），不只报总占比。
- 新增**同口径复算** `--compare a.json b.json`。
- 指纹含**口径常量**（防"改了尺子还报同一指纹"）。
- 效力条件**进代码**（`independence` 字段 + 自动效力标签）。
- 新增**最小可信样本线** `MIN_SAMPLES=40` 与**疑似率提示** `> 0.3`。
- 升版原因：v1.0 可被"只报一个数"与"自证数据"误用。

---

## v1.0 — 2026-10-10 · 初版

- 单指标：非关联候选占比。
- 口径写死到可复算（四类互斥 + 未知保守）。
- 不可核不猜。
- 取数适配器留空（只定义形状）。
