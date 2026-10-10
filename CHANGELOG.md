# CHANGELOG

本文件记录**协议口径**与**代码**的变更。口径变更必须升协议版本（口径指纹随之改变）。

---

## v2.2 — 2026-10-10 · **疑似单列**（口径变更 · ★ 持有方定义判）

> ★★ **这是本仓第一处真正的**口径**变更** ⇒ **口径指纹已变** ⇒
> **v2.2 之前的读数与之后的读数**不可比**（引用旧读数必须显式声明版本）。

**判词（持有方逐字）**：「**它既不该进分子，也不该简单进分母** —— **应该单列成一个独立出口**」
理由：**「把"不知道"渲染成一个具体的归属，就是做假读数」** ——
进分子＝把不确定读成"最好"· 进分母＝读成"最坏"· **两者是同一个错。**

### 口径（改了什么）

| ★ | v2.1 | **v2.2** |
|---|---|---|
| 分母 | `N`（含疑似/未知） | **`observed`** = `independent + marked_paid + 关联方`（**只含观测到的**） |
| 分子 | `independent + suspected` | **`independent`** |
| `suspected_paid` | 进分子 | **单列**（**不进分子、也不进分母**） |
| `unknown` | 按"非开放"保守计入 | **单列**；超限 ⇒ 该入口不可核 |
| `openness_strict` | `independent / N` | `independent / observed` ⇒ **与主口径同值** |
| 闸门 | 无 | **未知 > 0.2 或 疑似 > 0.5 ⇒ 该入口不可核** |

### 新增

- `UNKNOWN_MAX = 0.2` · `SUSPECTED_MAX = 0.5` —— ★ 两者**都进 `CALIBER`**（口径的一部分）。
- `CALIBER["observed_denominator"]` · `CALIBER["suspected_in"] = "single"` —— ★ 口径意图也进指纹。
- 输出新增 **`unknown_rate`**（★ 与 `suspected_rate` **并列**，★ 两者都必须随数报出）。
- **`logic_revision` r2 ⇒ r3**（★ 改计算逻辑必须动它）。

### 修正

- ★ **不可核的入口也必须交 `unknown_relations`** ——
  此前"未知超限"那条**早退**不带词表 ⇒ **拼错的 relation 恰恰在被拒的那一路看不见**（★ 正好倒过来）。

### 两条闸门的方向（★ 持有方特别点名）

★ **是「过多 ⇒ 不可核」，不是「存在 ⇒ 不可核」。**
若改成后者，闸门会**从"防误读"变成"防观测"** —— 入口只要把付费位标成"疑似"就能让读数作废。

### 测试

- `--selftest` ⇒ **`SELFTEST v2.2 : PASS`**
- `unittest` ⇒ **23 项 OK**（新增 3 条：未知未超限 / 未知超限 / 疑似过多）
- `test_mutation` ⇒ **7 项 OK**（★ 它们只喂 `independent`/`marked_paid` ⇒ 本次口径变更**不触及**其机制）

---

## 发布前体检 — 2026-10-10（同 v2.1.1 提交）

见 `docs/发布前清单.md`。本轮只做**不依赖决策**的整备：

- **版本号对齐**：`measure.py` `CODE_VERSION` 与 README 引用由 `2.1.0` 升到 **`2.1.1`**
  （此前 CHANGELOG 已到 v2.1.1，代码与 README 未同步）。
- **审核证据归档**：两轮探测脚本移入 `docs/审核证据/`（含 `probe-v20.py`、
  `probe-v21.py`、`mutation.py`、`rate_selftests.py`、`probe11.py`）并附 README。
- **README 文件结构表**补齐 `docs/发布前清单.md`、`docs/审核证据/`、`docs/原始素材/`。

### ⛔ 未解决（发布阻断项，需作者决策）

1. **口径分歧**：本仓库与用户 v2.1 定版对同一数据给出不同的数——
   `suspected_paid` 归属（分子 vs 分母）、`unknown` 处理（保守计入 vs 超限不可核）。
   **两套"同名不同口径"的尺子不得同时发布。**
2. ~~**许可署名**：`LICENSE` 版权人与 git user 仍为占位符。~~
   → **已解决（2026-10-10）**：`LICENSE` 版权人署 **NanshanJim**；
   git 提交身份为 **NanshanJim** + GitHub noreply（提交历史已一并重写）。
3. **未建远程仓库**：`git remote` 为空（待作者给仓库名与可见性）。

---

## v2.1.1 — 2026-10-10 · 变异测试回归修订

来源：`docs/代码审核报告-v21.md`（对**外部 v2.1 定版稿**的实机审核）。
本轮**新引入一套验证方法**，并用它查出了本仓库 v2.1 自己的 4 处漏洞。

### 新增（资产）
- **`docs/变异测试规范.md`**：自检有效性判据（L0 恒真 / L1 验结果 / L2 验机制）。
  判据：**一条自检若在"把被测机制拆掉"之后仍然通过，它就是无效的。**
- **`tests/test_mutation.py`**：7 条变异测试，逐条给出"前提 + 变异后必须失败"的对照。
- **`docs/代码审核报告-v21.md`**：外部定版的 10 项发现 + 13 条自检逐条评级。

### 本仓库自查（变异测试抓出的 4 处）
- **M1** 自证路径缺显式 `suppressed` 位（只有 `openness_main=None` 的影子）⇒ 补 `suppressed` 布尔。
- **M2** 读数指纹实际**未纳入 `independence`**（代码有该行，但入口把 `has_relation` 整个排除，
  导致 `openness*` 全为 None、指纹被"掏空后仍不同"）⇒ 修正效力语义 + 纳入指纹。
- **M3** `compare()` **未拦截自证读数**、且**未做完整性检查** ⇒ 补 `suppressed` 拦截与 `REQUIRED_FIELDS` 完整性闸。
- **M4** **`has_relation` 被过修**：协议只说 `provided_by_entry` 不入聚合，我却把 `has_relation`
  也整个排除了 ⇒ 恢复为"可用但降级为参考"（`in_aggregate=True`，flag 提示不得单独引用）。

> ★ **这 4 处全是本仓库 v2.1 自己引入的**——由变异测试在写完当天抓出，未流入下一版。

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
