# PROTOCOL · 候选集开放度口径协议

> 本文件是**规范**（normative）。`measure.py` 是它的一个实现。
> 两者冲突时，以本文件为准，并把实现缺陷记入 CHANGELOG。
> 当前协议口径：**v2.1**

---

## 1. 定义

**候选集开放度**测量：在同一购买意图下，**入口直接给出的候选**中，
非付费位、非关联方候选的占比。

它不测结果质量，只测"入口把多少位置留给中立候选"。

---

## 2. 样本与分母冻结

1. **分母冻结**：分母 `N = 入口直接给出的首轮候选总数`，**不含追问后结果**。
   翻页/追加结果如保留，必须单独字段标记并**默认排除**。
2. **不可核不猜**：任一入口样本为空 ⇒ 记 `uncomputable`，该入口**不出读数**，
   且**不得**用默认值补。全部入口为空 ⇒ 总读数 `null`。
3. **最小可信样本**：`MIN_SAMPLES = 40`（约 20 意图 × 至少 2 入口）；
   低于它 ⇒ 报 `样本不足`。`MIN_INTENTS = 20`。
   ★ 二者均为**工程默认值，无实测依据**，用起来后应逐步校准。

---

## 3. 判定规则（relation 词表）

每条候选必须落在下列 7 个 `relation` 值之一：

| relation | 归类 | 含义 |
|---|---|---|
| `independent` | independent | 中立候选 |
| `marked_paid` | paid | 入口自身标注的付费位 |
| `suspected_paid` | suspected | 无标注但具备可外部复核的推广特征（须有 `evidence`） |
| `self` | related | 自家 |
| `affiliate` | related | 返佣/联盟 |
| `equity` | related | 股权关联 |
| `exclusive` | related | 独家/排他 |

- 判定**可复算**：付费位以入口自身标注为准；关联方须有可复核规则（股权、实控人、广告主关系、返佣链接）。
- **疑似付费位证据化**：每条疑似必须有 `evidence`，并记录判定规则版本。
- **词表白名单**：不在词表内的值归入 `unknown`，**按"非开放"保守计入**，
  并写入 `unknown_relations` 与 `flags`（不静默吞掉）。
- ★ 归类表是口径的一部分，**参与口径指纹**。

---

## 4. 主口径 / 严格口径

```text
openness_main   = (independent + suspected) / N     ★ 头条指标
openness_strict =  independent            / N
suspected_rate  =  suspected              / N
spread          = max(per_entry_main) − min(per_entry_main)
```

- 主口径剔除"付费标注位 + 关联方"；**疑似计入分子**（其无付费标注）。
- 严格口径在主口径基础上**再扣疑似**。
- 疑似**单列**，默认不从分母剔除。
- `openness_overall` 是 `openness_main` 的**向后兼容别名**，二者恒等。

---

## 5. 报数纪律

一次合格读数**必须同时**给出：

`openness_main` · `openness_strict` · `per_entry_openness` · `spread` ·
`samples` · `intents` · `suspected_rate` · `uncomputable` · 口径指纹 ·
效力标签 · `unknown_relations`

★ 只报一个总占比 ⇒ 该读数视为**不完整**，不得引用。
★ 任一入口无可用样本 ⇒ 记入 `entries_without_data`，不得静默省略。

---

## 6. 效力标签（不得自证）

payload 增 `independence` 字段：

```text
independence = none / has_relation / provided_by_entry

  none              -> 读数可用
  has_relation      -> 参考（测量者与入口方有关系）
  provided_by_entry -> 【不算独立读数】，不参与任何聚合
```

★ `provided_by_entry` 的条目**被代码排除出** `openness_*`、`per_entry`、
`spread` 与全部计数，登记于 `excluded_from_aggregate`。
★ 本栏不得自填谎言：若事后发现声明不实，该测量者的**全部读数作废**。

---

## 7. 同口径复算

两个独立测量者用同一批意图、同一口径各跑一次，用
`measure.py --compare a.json b.json` 比对：

```text
口径指纹不同                      -> 不可比
任一读数效力不是 none             -> 不可比（拒收自证/关联读数）
|openness_main(a) − openness_main(b)| <= 0.05   -> 视为一致
```

★ `0.05` 是**工程默认值，无实证依据**；复算样本多了之后应由实测分布反推。
★ 只有"被独立复算过"的读数，才可用于对外引用。

---

## 8. 口径指纹与版本纪律

- **口径指纹** = `sha256(口径常量)`，其中口径常量**包含** relation 归类表与逻辑修订号。
- **读数指纹** = `sha256(口径指纹 + openness_main + openness_strict + spread +
  per_entry + samples + intents + independence)`。
- ★ **改任何一条口径规则（含归类表逻辑）⇒ 口径指纹必变**；
  ★ **结构不同（均匀 vs 两极）⇒ 读数指纹必不同**；
  ★ **效力状态不同 ⇒ 读数指纹必不同**。
- 修改判定规则必须**升协议版本**，不能事后调参。

---

## 9. 已知限度

- 无标注付费位会**高估**开放度；隐蔽关联方会**高估**开放度；
- 个性化会**破坏**可复现性；
- 只看"给出了哪些候选"，**不看**曝光、点击、排序权重、用户实际视野；
- 开放度高 ≠ 结果质量高；开放度低 ≠ 直接违法；
- 代码只能验**声明格式**，验不了**声明真假**（`independence` 栏的自证问题需外部锚）。

---

## 10. 变更记录

```text
v1.0 (2026-10-10)  初版：单指标 + 口径写死 + 不可核不猜 + 取数适配器留空
v2.0 (2026-10-10)  增：分布(spread/per_entry) / 复算 / 效力进代码 /
                       指纹含常量 / 样本线 / 疑似率提示
v2.1 (2026-10-10)  代码审核修订（详见 CHANGELOG.md）：
                   ① provided_by_entry 真正排除聚合（对齐 §6）
                   ② 口径指纹纳入 relation 归类表 + 逻辑修订号（对齐 §8）
                   ③ 读数指纹纳入分布与效力（对齐 §8）
                   ④ 并列报出主口径 openness_main / 严格口径 openness_strict（对齐 §4）
                   ⑤ compare() 拒收非独立读数（对齐 §7）
                   ⑥ relation 词表白名单校验 + 未知值告警（对齐 §3）
                   ⑦ 无数据入口显式登记（对齐 §5）
                   ⑧ CLI 兼容 --input/--output；⑨ 读文件友好报错
```
