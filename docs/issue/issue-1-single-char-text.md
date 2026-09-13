# 单字符文本节点被序列化丢弃——len(text)>1 过滤器误杀个位数表格数值（qty/计数列整体消失）

> Issue：[dom-snapshot#1](https://github.com/zjordon/dom-snapshot/issues/1)
> 状态：OPEN ｜ 提交人：zjordon ｜ 创建时间：2026-09-13
>
> 本文件为 issue 原文存档，正文与 GitHub 保持一致（无评论）。
> 修复方案见 [docs/bug-fix/issue-1-single-char-text.md](../bug-fix/issue-1-single-char-text.md)。

## 现象

TreeWalker（WebArena shopping_admin 评测）实测：报表网格的**个位数数值单元格**在 element_tree_text 中整体消失，而同表其他列（多字符文本 / 多位数）正常。agent 看到的表格数值列为空，被迫自创替代口径（如「行数=销量」），直接造成评测判 0（zjordon/TreeWalker#184 现象③的移交定位）。

## 证据链（2026-09-13 真机三对照）

页面：Magento admin Bestsellers Report（localhost:7780，年度筛选，5 行数据）。

1. **原始 DOM 有值**（CDP Runtime.evaluate 读 outerHTML）：Order Quantity 列逐行 `4/3/3/2/2`，形如 `<td class=" col-qty col-qty_ordered col-number">\n                                4                                </td>`（裸文本子节点，前后大量空白）；tfoot 合计 `Total 14`——4+3+3+2+2=14 精确吻合，服务端渲染与聚合数据均无问题；
2. **快照丢的恰好全是 len==1 的文本**：qty 五个值（4/3/3/2/2）全丢；网格头 `1 records found` 的 `1` 也丢；而 `14`（len 2）、`2023`（span 内，len 4）、`$14.00`（len 5）、商品名（多字符）全部保留——**分界线就是 strip 后字符数**；
3. **代码定位**：`src/dom_snapshot/serializer.py:243`（TEXT_NODE 建树保留条件）与 `serializer.py:1068-1070`（渲染时同条件二道门）：

   ```python
   is_visible
   and node.node_value
   and node.node_value.strip()
   and len(node.node_value.strip()) > 1   # ← 单字符一律丢弃
   ```

   单字符文本节点在建树阶段即被丢弃，任何路径到不了模型。

## 影响面

所有**个位数数值（0-9）**静默丢数据：订单/报表 qty 列（个位销量极常见）、库存数、评分、`N records found` 计数（N<10 时）。多位数（10+）不受影响——这解释了问题为何时隐时现。TreeWalker 侧历史谜团（data_truncated 失败分析中 task 128 的 qty 疑云）大概率同源。

## 根因来历

`git log -L 236,247` 显示该条件源自 M2 迁移原始代码（browser-use 血统的单字符噪声过滤，意图滤 `•`/`|`/`·` 装饰符），无测试锁定行为。

## 修复建议

- 谓词改为 `len(text) > 1 or text.isalnum()`：个位数/单字母保留，装饰单字符（非 alnum）照滤，噪声过滤意图不破（CJK 单字按 Unicode `isalnum` 也保留，属合理增益）；
- 两处同改（建树 243 + 渲染 1070），或删除渲染层二道门；
- 补单测：个位数保留 / 装饰单字符仍滤 / 空白文本仍滤；
- 发版后 TreeWalker bump 依赖重跑复验。

## 复现材料

- 环境：Windows + Chrome 9223（CDP）+ Magento admin 报表页；
- 只读探针（TreeWalker 仓）：`examples/p7_probe_report_qty_column.py`（qty 单元格 outerHTML / uiRegistry / 快照三对照）；
- 快照现场：TreeWalker 仓 `examples/_model_page_view.txt`（qty `<td />` 空 vs DOM 有值）。

## 关联

- zjordon/TreeWalker#184 现象③（本 issue 为其根因移交）；该 issue 现象①②（modal re-hide / 折叠区骨架）经产品裁决为 by-design（非可见元素不进快照是既定语义），与本仓无关。
