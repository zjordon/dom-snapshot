# M2 实施计划：核心抽取（5 文件迁移 + 3 耦合点处理 + 内部测试）

> 本文档是 ROADMAP.md 中 **M2 阶段**的详细实施方案，基于 M2.1 依赖核实（对 TreeWalker
> `src/tree_walker/browser/` 源码的实地调研）制定。M1（仓库脚手架）已完成，本文档供 M2 实施时参照执行。
>
> 制定日期：2026-07-29。M2.1 核实来源：本仓库 `ARCHITECTURE.md` + TreeWalker 源码实地核对。

## 范围与边界

**本次只做 dom-snapshot 仓库内的迁移 + 内部测试（ROADMAP M2.2 + M2.3）**，不含 TreeWalker 接入（M3 单独做）。
完成后 dom-snapshot 内部能独立运行 `build_dom_state`，但 TreeWalker 仍用本地旧代码（互不影响）。

5 个源文件（共 3453 行，与 ROADMAP 记载一致）：

| 源文件（TreeWalker `src/tree_walker/browser/`） | 行数 | 迁入 |
|---|---|---|
| `views.py`（DOM 部分） | 830 | `dom_snapshot/models.py` |
| `cdp_timeout.py` | 195 | `dom_snapshot/cdp_timeout.py` |
| `paint_order.py` | 200 | `dom_snapshot/paint_order.py` |
| `dom.py` | 1055 | `dom_snapshot/collector.py` + `interactive.py` |
| `serializer.py` | 1173 | `dom_snapshot/serializer.py` |

---

## M2.1 依赖核实结论（抽取前的关键调研，已完成）

### 核实点 1：`client.send` 调用形式 —— **属性链式**（推翻 ARCHITECTURE 现写法）

TreeWalker 全部 11 处 `client.send` 调用都是属性链式：

```python
await client.send.DOM.getDocument({'depth': -1, 'pierce': True}, session_id=session_id)
await client.send.DOMSnapshot.captureSnapshot({...}, session_id=session_id)
await client.send.Accessibility.getFullAXTree({'frameId': fid}, session_id=session_id)
await client.send.Runtime.evaluate({...}, session_id=session_id)
await client.send.DOM.describeNode({'objectId': oid}, session_id=session_id)
# ...Page.getLayoutMetrics / Page.getFrameTree / Runtime.getProperties / Runtime.releaseObject
#    Target.getTargets / Target.attachToTarget / Target.detachFromTarget
```

**结论**：`client.send` 不是可调用方法，而是**属性对象**（cdp-use 的 `CDPLibrary`），含各 Domain 子对象，
每个子对象的方法签名为 `async def m(self, params: dict | None = None, session_id: str | None = None) -> dict`，
返回 coroutine，await 后得 dict。**不存在任何参数式 `client.send("DOM", ...)` 调用。**

cdp-use 源码佐证（`.venv/Lib/site-packages/cdp_use/`）：
- `client.py:249` `self.send: "CDPLibrary" = CDPLibrary(self)`
- `cdp/library.py` `CDPLibrary.__init__` 为每个 Domain 挂一个 client：`self.DOM = DOMClient(client)` …
- 各 Domain 方法签名统一（如 `dom/library.py:268`）：
  `async def getDocument(self, params: Optional["GetDocumentParameters"] = None, session_id: Optional[str] = None) -> "GetDocumentReturns"`
  运行时 params 接受 dict（底层 `send_raw` 序列化），类型层用 typed Parameters 类（字符串前向引用）。

dom.py 中 `client` 类型注解为 `client: CDPClient`，`from cdp_use import CDPClient`（dom.py:21）。

### 核实点 2：`views.py` 拆分清单 —— 基本准确，发现 3 处 ARCHITECTURE 偏差

逐类核对结果（`views.py` 共 830 行）：

**进 `dom_snapshot/models.py`（纯 dataclass / Enum / 常量，零 pydantic）：**

| 对象 | 类型 | views.py 行号 |
|---|---|---|
| `DEFAULT_INCLUDE_ATTRIBUTES` | list 常量 | L25-80 |
| `STATIC_ATTRIBUTES` | set 常量 | L82-131 |
| **`DYNAMIC_CLASS_PATTERNS`** | frozenset 常量 | L133-156 |
| `NodeType` | `int, Enum` | L162-176 |
| `filter_dynamic_classes` | function | L189-195 |
| `DOMRect` | `@dataclass(slots=True)` | L201-212 |
| `EnhancedAXProperty` | `@dataclass(slots=True)` | L218-223 |
| `EnhancedAXNode` | `@dataclass(slots=True)` | L226-236 |
| `EnhancedSnapshotNode` | `@dataclass(slots=True)` | L242-253 |
| `EnhancedDOMTreeNode` | `@dataclass`（25 字段） | L259-620 |
| `DOMSelectorMap` | alias `dict[int, EnhancedDOMTreeNode]` | L625 |
| `SimplifiedNode` | `@dataclass(slots=True)` | L631-664 |
| `PropagatingBounds` | `@dataclass` | L667-674 |
| `FileInputInfo` | `@dataclass` | L680-694 |
| `SerializedDOMState` | `@dataclass` | L697-713 |
| `DOMDegradationLevel` | `Enum` | L806-811 |
| `DOMCollectionConfig` | `@dataclass` | L814-820 |
| `DOMCollectionMetrics` | `@dataclass` | L823-830 |

**留 TreeWalker（`browser/views.py`）：**

| 对象 | 类型 | views.py 行号 | 说明 |
|---|---|---|---|
| `DOMInteractedElement` | **`@dataclass`**（非 pydantic） | L716-765 | 留此（agent 运行时指纹），读 `EnhancedDOMTreeNode` |
| `MatchLevel` | `Enum` | L179-186 | 漏列项，留此（rerun.py 用） |
| `TabInfo` | pydantic `BaseModel` | L771-774 | |
| `BrowserEvent` | pydantic `BaseModel` | L777-789 | |
| `BrowserStateSummary` | pydantic `BaseModel` | L792-801 | `dom_state` 字段引用移出的 `SerializedDOMState`（已有 `arbitrary_types_allowed=True`） |

#### ⚠️ 3 处 ARCHITECTURE.md 偏差（迁移前必须修正，否则 NameError / 误导）

1. **`DYNAMIC_CLASS_PATTERNS`（L133-156）漏列** —— `filter_dynamic_classes`（L194）依赖它：
   `not any(pattern in c.lower() for pattern in DYNAMIC_CLASS_PATTERNS)`。
   迁移时**必须携带**进 models.py，否则 `filter_dynamic_classes` 报 `NameError`。
2. **`MatchLevel`（L179-186）漏列** —— 历史 rerun.py 使用，留 TreeWalker。
3. **`DOMInteractedElement` 是 `@dataclass`，不是 pydantic** —— 位置（留 TreeWalker）正确，但理由错。
   `from pydantic import BaseModel, Field`（L20）仅被 `TabInfo`/`BrowserEvent`/`BrowserStateSummary` 使用。

#### 依赖污染检查（结论：零污染）

- `views.py` import 区（L12-20）：仅 stdlib + `from pydantic import BaseModel, Field`（L20）。
- **没有任何 dom-snapshot 候选类使用 pydantic**（无 `BaseModel` 继承、无 `Field(...)` 调用）。
  所有工厂默认值都用 dataclass `field(default_factory=...)`。
- **无跨模块引用**（无 `from .session import` / `from .dom import`）。
- **剥离 pydantic = 删 L20 一行**。迁出后 models.py 仅需 `hashlib/uuid/dataclasses/enum/typing`。

#### `DOMInteractedElement.load_from_enhanced_dom_tree`（views.py:749-765）读的 EnhancedDOMTreeNode 字段

直接读：`node_id` / `backend_node_id` / `frame_id` / `node_type` / `node_value` / `node_name` /
`attributes` / `ax_node.name` / `snapshot_node.bounds`（9 个，全在 25 字段内）。
间接读（via `node.xpath` / `hash(node)` / `compute_stable_hash()`）：`parent_node` 链、`node_name`/tag_name、
`STATIC_ATTRIBUTES`、`filter_dynamic_classes`、`ax_node.name`。
**这些字段都必须进 dom-snapshot 的 `EnhancedDOMTreeNode`**——无一例外。

#### `EnhancedDOMTreeNode` 完整 25 字段（selector_map value 类型，最关键）

必需（无默认）：`node_id`、`backend_node_id`、`node_type`、`node_name`、`node_value`、`attributes`
有默认：`is_scrollable`、`is_visible`、`ignored_by_paint_order`、`absolute_position`、`target_id`、
`frame_id`、`session_id`、`content_document`、`shadow_root_type`、`shadow_roots`、`parent_node`、
`children_nodes`、`ax_node`、`snapshot_node`、`has_js_click_listener`、`_compound_children`、
`hidden_elements_info`、`has_hidden_content`、`uuid`
另携带方法/属性：`tag_name`、`xpath`、`compute_stable_hash`、`__hash__` 等（DOMInteractedElement 间接用，原样保留）。

### 核实点 3：iframe target 函数 —— 提为 public API（已决策）

`_build_frame_target_map`（dom.py:539-559）与 `_attach_to_iframe_target`（dom.py:562-571）：

- **纯 CDP Target API 薄封装**：仅依赖 `client` + 各一个 CDP 调用（`Target.getTargets` / `Target.attachToTarget`），
  无 dom.py 内部符号依赖。异常兜底返回 `{}, {}` / `None`。
- **dom.py 内部采集也用**：`build_dom_state`（dom.py:1024）调 `_build_frame_target_map`；
  `_build_enhanced_dom_tree`（dom.py:934）调 `_attach_to_iframe_target` 做跨源 iframe 递归采集。
- **session.py 也用**（session.py:23-25 import；2834/2840 调用）：`evaluate(frame=...)` 进 iframe 执行 JS。

session.py 对 dom/serializer/views 的完整跨模块依赖：

| 符号 | 来源 | 用途 |
|---|---|---|
| `_attach_to_iframe_target` | dom.py | evaluate 进 iframe（L2840） |
| `_build_frame_target_map` | dom.py | frameId→targetId 解析（L2834） |
| `build_dom_state` | dom.py | get_state 主入口（L1597） |
| `EMPTY_DOM_STATE` | dom.py | 熔断兜底（L1593/1609 懒导入） |
| `BrowserEvent`/`BrowserStateSummary`/`DOMCollectionConfig`/`DOMDegradationLevel`/`DOMRect`/`DOMSelectorMap`/`TabInfo` | views.py | 类型 |

**session.py 不引用 serializer.py 任何符号**（序列化对 session 是黑盒，只通过 `build_dom_state` 返回值消费）。

`build_dom_state` 主入口签名（dom.py:1003-1009）：
```python
async def build_dom_state(
    client: CDPClient,
    session_id: str | None = None,
    viewport_threshold: int | None = 1000,
    previous_selector_map: DOMSelectorMap | None = None,
    config: DOMCollectionConfig | None = None,
) -> tuple[SerializedDOMState, DOMCollectionMetrics]:
```

---

## 已确认的 3 个关键决策

| # | 决策点 | 选择 | 理由 |
|---|---|---|---|
| 1 | Protocol 建模 | **完整多级 Protocol（逐 Domain 建模）** | `client.send` 是属性链式。为 DOM/DOMSnapshot/Accessibility/Runtime/Page/Target 六个 Domain 各建子 Protocol，每个含 dom.py 实际调用的 async 方法。方法参数用 `dict \| None`（不绑 cdp-use 的 typed Parameters 类，保零硬依赖），返回 `dict`。类型安全最强。 |
| 2 | iframe target 函数 | **提为 public API（去下划线）** | 纯 CDP 薄封装，dom 内部采集也用。`build_frame_target_map` / `attach_to_iframe_target` 进 `__init__.py`。M3 时 session.py 改 import 路径即可，调用点零改动。 |
| 3 | 实施边界 | **只做 M2（dom-snapshot 内部），不含 TreeWalker 接入** | M2/M3 分阶段独立验收、可回滚。本次完全不动 TreeWalker。 |

---

## M2.2 逐文件迁移步骤（按依赖顺序，自底向上）

### 步骤 0：修正 ARCHITECTURE.md 的 3 处偏差
- 拆分清单表格补 `DYNAMIC_CLASS_PATTERNS`（进 models.py）
- 补 `MatchLevel`（留 TreeWalker）
- 修正耦合点 2 文字：`DOMInteractedElement` 是 dataclass（非 pydantic）
- 修正第三节 Protocol 代码示例：参数式 → 属性链式 + 多级 Protocol

### 步骤 1：`models.py`（从 views.py 迁入，零 pydantic）
迁入 views.py 的 L12-19 stdlib import + L23-195 常量/函数 + L198-713 dataclass + L804-830 Enum/dataclass，
**删 L20 `from pydantic import BaseModel, Field`**。含补漏的 `DYNAMIC_CLASS_PATTERNS`。
仅依赖 stdlib（hashlib/uuid/dataclasses/enum/typing）。

### 步骤 2：`cdp_timeout.py`（零改动迁移）
原样复制（195 行）。仅 stdlib 依赖（asyncio/logging/time/collections/dataclasses/enum），无内部 import。

### 步骤 3：`_protocol.py`（新建完整多级 Protocol）
- 六个 Domain 子 Protocol：`_DOMDomain`（getDocument/describeNode）、`_DOMSnapshotDomain`（captureSnapshot）、
  `_AccessibilityDomain`（getFullAXTree）、`_RuntimeDomain`（evaluate/getProperties/releaseObject）、
  `_PageDomain`（getLayoutMetrics/getFrameTree）、`_TargetDomain`（getTargets/attachToTarget/detachFromTarget）
- 每个方法签名：`async def m(self, params: dict | None = None, *, session_id: str | None = None) -> dict`
- `_CDPLibrary` Protocol 聚合六个 Domain 属性
- `CDPLikeClient` Protocol：`send: _CDPLibrary`
- `cdp_use.CDPClient` 仅 `TYPE_CHECKING` 引用（不硬依赖）

### 步骤 4：`paint_order.py`（仅 import 调整）
原样复制（200 行）。`from tree_walker.browser.views import SimplifiedNode` → `from dom_snapshot.models import SimplifiedNode`。

### 步骤 5：`interactive.py`（从 dom.py:74-218 抽出，破循环依赖）
抽 `ClickableElementDetector`（L74-213）+ `is_interactive`（L216-218）到独立文件。
import `from dom_snapshot.models import EnhancedDOMTreeNode, NodeType`。
**破循环关键**：collector 和 serializer 都从此导入，循环消失。

### 步骤 6：`collector.py`（原 dom.py 主体，调整 import）
复制 dom.py 全文剔除已抽走的 interactive 部分（L74-218）。import 调整：
- `from cdp_use import CDPClient` → 删除；`from dom_snapshot._protocol import CDPLikeClient`；
  函数签名 `client: CDPClient` → `client: CDPLikeClient`
- `from tree_walker.browser.views import (...)` → `from dom_snapshot.models import (...)`
- `from tree_walker.browser.cdp_timeout import run_cdp_batch` → `from dom_snapshot.cdp_timeout import run_cdp_batch`
- `from tree_walker.browser.serializer import DOMTreeSerializer`（L1037 懒导入）→ `from dom_snapshot.serializer import DOMTreeSerializer`
- 两个 iframe 函数去下划线提 public：`_build_frame_target_map`→`build_frame_target_map`、
  `_attach_to_iframe_target`→`attach_to_iframe_target`，同步改内部调用点（L934、L1024）
- `EMPTY_DOM_STATE` 定义保留在此（顶层）

### 步骤 7：`serializer.py`（原 serializer.py，调整 import + 破循环）
复制 serializer.py 全文（1173 行）。import 调整：
- `from tree_walker.browser.views import (...)` → `from dom_snapshot.models import (...)`
- `from tree_walker.browser.dom import is_interactive`（L688 懒导入）→ `from dom_snapshot.interactive import is_interactive`
  （**循环依赖消除**：不再懒导入 collector，改从 interactive 直接导入）

### 步骤 8：`__init__.py`（补全 public API）
按 ARCHITECTURE 第四节导出：`build_dom_state`、`EMPTY_DOM_STATE`、`build_frame_target_map`、
`attach_to_iframe_target`、全部数据模型、`CDPLikeClient`。

---

## M2.3 内部测试计划

- `tests/test_models.py`：dataclass 构造、`filter_dynamic_classes`、`EnhancedDOMTreeNode.compute_stable_hash`/`xpath`/`__hash__`（DOMInteractedElement 间接读的字段）
- `tests/test_interactive.py`：14 条规则关键路径 + 边界（非 ELEMENT_NODE、html/body 排除、js click listener、label、AX role 等）
- `tests/test_cdp_timeout.py`：`run_cdp_batch` 两阶段超时 + 重试（用假 async factory，不连真 CDP）
- `tests/test_protocol.py`：FakeClient（实现 Protocol）符合 `isinstance` 检查
- `tests/test_smoke_import.py`：`import dom_snapshot` 全链路无 CircularImport；`build_dom_state` 可导入

**抽取等价性**：因 fixture 需从 TreeWalker 录制 CDP 响应（跨工程），本次先建 `tests/fixtures/` 目录 +
conftest 占位。完整等价性测试在 fixture 就绪后补（或 M3 时用 TreeWalker 现有 fixture 验证）。
本次保证各模块单测通过 + 无 import 循环。

---

## 验收标准

- `uv run python -c "import dom_snapshot"` 无循环 import
- `uv run ruff format --check .` + `uv run ruff check .` 全过
- `uv run python -m pytest tests/ -v` 全过
- 更新 ROADMAP.md：勾选 M2.2/M2.3 已完成项，M2 状态 → ✅

---

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| 循环 import 残留 | interactive.py 独立后，用 `python -c "import dom_snapshot"` + 逐模块 import 验证 |
| 字段遗漏 | models.py 严格对照核实点 2 的 EnhancedDOMTreeNode 25 字段清单 + DYNAMIC_CLASS_PATTERNS 补漏 |
| Protocol 方法覆盖不全 | 严格对照核实点 1 的 dom.py 11 处调用点，确保六个 Domain 方法不遗漏 |
| 剥离 pydantic 残留 | models.py 迁入后 `grep pydantic` 确认零引用 |
| 不动 TreeWalker | 本次完全不改 TreeWalker 仓库，无回归风险 |

---

## 不做（明确排除）

- 不改 TreeWalker 任何文件（M3 范围）
- 不连真浏览器（测试用假 factory/对象）
- 不做抽取等价性的 byte-for-byte 验证（需 TreeWalker fixture，M3 时做）
- 不 git commit（按 AGENTS.md，除非用户明确要求）
