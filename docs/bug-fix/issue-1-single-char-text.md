# Issue #1 修复实施方案：单字符文本节点被序列化丢弃

> 对应 issue：[dom-snapshot#1](https://github.com/zjordon/dom-snapshot/issues/1)
> （根因自 TreeWalker#184 现象③移交）
>
> 分支：`fix/issue-1-single-char-text`（基于 main @ 32ee19f）
> 制定日期：2026-09-13。分析已完成实证复现，本方案直接可执行。

## 一、问题回顾（已实证）

`serializer.py` 对 TEXT_NODE 的保留条件含 `len(text.strip()) > 1`，导致 strip 后恰好
1 字符的可见文本在建树阶段即被丢弃。复现结论（最小用例，Magento 报表 qty 列场景）：

| 单元格内容 | 产出 | 判定 |
|---|---|---|
| `4` / `3`（个位数） | `[100]<td />` 空壳，数值消失 | ❌ 误杀 |
| `14`（len 2） | `14` 保留 | ✓ |
| `Total`（len 5） | `Total` 保留 | ✓ |
| `•`（装饰符） | 丢弃 | ✓ 原意图 |

附加细节：丢弃文本后 `<td />` 空壳仍留在树里——模型看到"表格有这一列但值为空"，
比整行消失更误导（agent 被迫自创替代口径，WebArena 评测直接判 0）。

影响面：所有 strip 后 1 字符的文本静默丢失——个位数 **0-9**（含 0）、单字母
（尺码 M/L/S）、`N records found` 的 N<10。多位数不受影响（bug 时隐时现的原因）。

## 二、根因（两处，已定位）

```python
# serializer.py:243  Step 1 建树（_create_simplified_tree 的 TEXT_NODE 分支）
and len(node.node_value.strip()) > 1

# serializer.py:1070  serialize_tree 渲染（TEXT_NODE 分支，同条件二道门）
and len(node.original_node.node_value.strip()) > 1
```

来历：逐字继承自 TreeWalker 原版 serializer.py（browser-use 血统的单字符装饰符
噪声过滤，意图滤 `•`/`|`/`·`）。**非 M2 迁移引入的回归**——迁移纯重组，byte-for-byte
等价性验证恰恰保证了 bug 被"忠实"搬运。全库仅这两处长度过滤（已 grep 确认，影响面封闭）。

## 三、修复方案

### 3.1 核心改动：抽共享谓词 + 两处调用（优于 issue 原案的"两处同改"）

在 `serializer.py` 模块级辅助函数区（`_safe_parse_number` 附近）新增：

```python
def _is_meaningful_text(value: str) -> bool:
    """文本节点是否值得进入文本树。

    单字符噪声过滤：多字符一律保留；单字符仅保留字母/数字（含 CJK，
    Unicode isalnum），装饰符（•、|、· 等）仍滤——继承 browser-use 噪声
    过滤意图，同时不再误杀个位数数值（issue #1）。
    """
    text = value.strip()
    return len(text) > 1 or text.isalnum()
```

两处调用点改为（保持各自前置条件 `node_value` / `strip()` 非空由谓词内部的
`text = value.strip()` + `len(text) > 1 or ...` 自然涵盖——空串 `len==0` 且
`''.isalnum()` 为 False，返回 False，行为不变）：

```python
# :239-244（建树）
if (
    is_visible
    and node.node_value
    and _is_meaningful_text(node.node_value)
):
    return SimplifiedNode(original_node=node, children=[])

# :1066-1071（渲染）
if (
    is_visible
    and node.original_node.node_value
    and _is_meaningful_text(node.original_node.node_value)
):
    parts.append(f"{indent}{node.original_node.node_value.strip()}")
```

**决策说明**：
- 选 `isalnum()` 而非更窄的 `isdigit()`——后者会误杀单字母（尺码 M/L/S、单位）
- 渲染层二道门**保留**（防御纵深），但两处共用同一谓词后永远不会再失同步
- CJK 单字按 Unicode `isalnum()` 保留（"男"/"女"等单字值），属合理增益（issue 已认可）

### 3.2 边界行为核对（改后）

| 输入（strip 后） | 改前 | 改后 | 依据 |
|---|---|---|---|
| `4` / `0` / `9` | 丢 | **留** | `isalnum()` True |
| `M` / `L` / `男` | 丢 | **留** | `isalnum()` True |
| `•` / `\|` / `·` | 丢 | 丢（不变） | `isalnum()` False |
| `""` / 纯空白 | 丢 | 丢（不变） | `len==0` 且 `isalnum()` False |
| `14` / `Total` | 留 | 留（不变） | `len > 1` |
| `$`（孤立货币符） | 丢 | 丢（不变） | 非 alnum，孤立无信息量，可接受 |

## 四、测试计划（新增 `tests/test_text_filter.py`）

现确认现有 90 项测试无一覆盖文本节点过滤（修复不碰任何现有断言）。新增用例：

1. **个位数保留**：`<td>` 内裸文本 `"  4  "`（前后空白）→ element_tree_text 含 `4`
2. **含 0**：`"0"` 保留（qty=0 场景）
3. **单字母/CJK 保留**：`"M"`、`"男"` 保留
4. **装饰单字符仍滤**：`"•"`、`"|"` 不出现
5. **纯空白仍滤**：`"   "` 不产出节点
6. **多字符行为不变**：`"14"`、`"Total"` 保留（防回归锚点）
7. **建树与渲染一致性**：改后建树（:243）与渲染（:1070）经同一谓词——
   单测直接断言最终 element_tree_text（同时覆盖两道门）
8. **`_is_meaningful_text` 单元级**：上表全部边界逐行断言

测试复用本次分析中的最小树构造法（可见 snapshot + `is_visible=True` 的
td/文本节点组合），不连真浏览器，符合 AGENTS.md 测试约定。

## 五、实施顺序

1. `serializer.py`：新增 `_is_meaningful_text` + 改两处调用
2. `tests/test_text_filter.py`：新增上述用例
3. 全量验收：
   - `uv run ruff format --check .` + `uv run ruff check .`
   - `uv run python -m pytest tests/ -v`（原 90 项 + 新增全过）
   - 重跑本次分析的最小复现脚本：`4`/`3` 保留、`•` 仍滤（人工对照）
4. ROADMAP 无需改动（bug 修复不在里程碑内）；可在 issue #1 回帖附修复 commit
5. **发版 v0.1.1**（SemVer PATCH，走 `/release` 流程）：
   - `pyproject.toml` version → 0.1.1
   - CHANGELOG.md（新建）：记录 fix
   - tag `v0.1.1` + push
6. **通知 TreeWalker 侧**：bump `dom-snapshot` 依赖至 v0.1.1，重跑
   `examples/p7_probe_report_qty_column.py` 三对照复验（qty 列 4/3/3/2/2 回归）

## 六、风险与权衡

| 风险 | 评估 | 缓解 |
|---|---|---|
| 破坏 byte-for-byte 等价性 | **必然且有意**——旧一致是"带着 bug 的一致" | 发版后 TreeWalker bump，双方同时进入新基线 |
| 单字符噪声（装饰符）重新漏进文本树 | 无——非 alnum 单字符仍滤 | 测试用例 4 锁定 |
| 文本树体积增长 | 极小——仅新增单字符 alnum 文本 | 无需处理 |
| 无现有测试锁定旧行为 | 已确认（grep tests/ 零覆盖） | 新用例直接锁定新行为 |
| 影响面外溢 | 无——全库仅两处长度过滤，皆在改动内 | 已 grep 确认 |

## 七、验收标准

- [ ] `tests/test_text_filter.py` 全过（8 类用例）
- [ ] 原 90 项测试全过（无回归）
- [ ] ruff format/check 全过
- [ ] 最小复现脚本对照：`4`/`3` 保留、`•`/空白 仍滤、`14`/`Total` 不变
- [ ] v0.1.1 发版（tag + push）
- [ ] issue #1 回帖闭环（附 commit + 版本号）
- [ ] TreeWalker bump 后 qty 列复验通过（跨仓步骤，由 TreeWalker 侧执行）
