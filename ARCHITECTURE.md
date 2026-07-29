# dom-snapshot 架构设计

> 本文档详述 dom-snapshot 的内部架构、数据流、抽取自 TreeWalker 的 3 个耦合点处理、
> 以及 public API 设计。是开发该库的主要技术参考。
>
> 方案来源：[treeforge/docs/p2/README.md](https://github.com/zjordon/treeforge/blob/main/docs/p2/README.md) 第 3.1 节。

## 一、核心数据流

```
CDPLikeClient（鸭子类型，任何 CDP 客户端）
    │
    ▼
build_dom_state(client, session_id, prev_map, cfg)        ← collector.py 公开入口
    │
    ├─ Phase 1: _detect_js_click_listeners()              ← 内联 JS 检测 Vue@click/React onClick
    │
    ├─ Phase 2: _collect_cdp_sources()                    ← 三源并行采集
    │     ├─ 源1: DOM.getDocument(depth=-1, pierce=True)  ← 父子结构 + shadow DOM（权威树）
    │     ├─ 源2: DOMSnapshot.captureSnapshot             ← 布局/可见性/坐标/paintOrder
    │     └─ 源3: Accessibility.getFullAXTree              ← 语义角色/名称/状态
    │     （三源通过 backendNodeId 交叉引用）
    │
    ├─ Phase 3: _construct_enhanced_node()                ← 三源融合递归成 EnhancedDOMTreeNode
    │     ├─ _build_snapshot_lookup()
    │     ├─ _build_ax_lookup()
    │     └─ _collect_file_inputs()                       ← [File Inputs] 数据源
    │
    └─ Phase 4: DOMTreeSerializer(root).serialize_accessible_elements()  ← serializer.py
          ├─ Step 1: _create_simplified_tree              ← 过滤 script/style/SVG 子元素 + 可见性剪枝
          ├─ Step 2: PaintOrderRemover.calculate_paint_order  ← 几何差集标记被遮挡节点
          ├─ Step 3: _optimize_tree                       ← 后序遍历剪除空叶容器
          ├─ Step 4: _apply_bounding_box_filtering        ← 传播型元素包围盒合并（<a>/<button>）
          ├─ Step 5: _assign_interactive_indices          ← 给可交互元素编号 + 写 selector_map
          │
          └─ serialize_tree()                             ← 产出 element_tree_text
                ├─ 主格式：[index]<tag attr=val /> text
                ├─ 新元素前缀 *（对比 prev_map）
                ├─ 可滚动标记 |scroll element|
                ├─ 复合组件 compound_components=(...)
                ├─ Shadow DOM 边界 Open/Closed Shadow
                └─ SVG 折叠 <!-- SVG content collapsed -->
                                    │
                                    ▼
                        SerializedDOMState
                        ├─ element_tree_text   ← 给 LLM 看的文本树
                        ├─ selector_map        ← index → EnhancedDOMTreeNode（定位用）
                        ├─ file_inputs_meta    ← [File Inputs] 段数据
                        └─ page_stats          ← [Page Stats] 段数据
```

**降级机制**：FULL（三源全有）→ MINIMAL（snapshot 缺失）→ PARTIAL（AX 缺失）→ FAILED（DOM 树缺失）。
采集失败不抛异常，返回 `EMPTY_DOM_STATE`（collector.py 顶部定义）。

## 二、模块分层

```
dom_snapshot/
├── __init__.py            # public API（build_dom_state + 数据模型 + Protocol）
├── _protocol.py           # CDPLikeClient Protocol（解耦 cdp-use）
├── models.py              # DOM 数据模型（纯 dataclass，从 views.py 拆出）
├── cdp_timeout.py         # 两阶段超时批处理（零内部依赖）
├── paint_order.py         # Step 2 遮挡算法（仅依赖 models.SimplifiedNode）
├── interactive.py         # ClickableElementDetector + is_interactive（从 dom.py 抽出，破循环依赖）
├── collector.py           # 原 dom.py：三源采集 + 增强树构建（依赖 cdp_timeout + models + interactive）
└── serializer.py          # 原 serializer.py：五步过滤 + 文本格式化（依赖 models + paint_order + interactive）
```

**依赖方向**（无循环）：

```
_protocol.py   ← 零依赖
models.py      ← 零依赖（仅 stdlib: dataclasses/hashlib/uuid）
cdp_timeout.py ← 零依赖
paint_order.py ← models
interactive.py ← models
collector.py   ← _protocol + models + cdp_timeout + interactive + serializer（懒导入）
serializer.py  ← models + paint_order + interactive（懒导入 collector.is_interactive 已移走）
```

## 三、三个耦合点处理（抽取自 TreeWalker 的关键工作）

### 耦合点 1：`dom.py ↔ serializer.py` 循环依赖

**TreeWalker 现状**：
- `dom.py:1037` 懒导入 `DOMTreeSerializer`（serialize 阶段调）
- `serializer.py:688` 懒导入 `dom.is_interactive`（Step 5 编号时调）

**dom-snapshot 处理**：把 `is_interactive` / `ClickableElementDetector`（TreeWalker `dom.py:74-218`）
独立成 `dom_snapshot/interactive.py`。collector.py 和 serializer.py 都从 interactive.py 导入，循环消失。

```python
# dom_snapshot/interactive.py（新文件，从 dom.py 抽出）
class ClickableElementDetector:
    """检测元素是否可交互：cursor:pointer / onclick / Vue@click / React onClick 等。"""
    ...

def is_interactive(node) -> bool:
    """综合判定节点是否可交互（Step 5 编号用）。"""
    ...
```

### 耦合点 2：`views.py` 混合两类模型

**TreeWalker 现状**：`views.py` 同时含
- DOM 快照核心（纯 dataclass）：`EnhancedDOMTreeNode` / `SimplifiedNode` / `SerializedDOMState` / `FileInputInfo` / `DOMRect` 等
- 浏览器聚合状态（pydantic）：`BrowserStateSummary` / `TabInfo` / `BrowserEvent` / `DOMInteractedElement`

**dom-snapshot 处理**：`views.py` 拆两半——
- DOM 核心进 `dom_snapshot/models.py`（随库走，纯 dataclass，零 pydantic 依赖）
- 聚合状态留在 TreeWalker 的 `browser/views.py`（这些是 agent 运行时概念，不属于快照库）

**拆分清单**（需在抽取时精确执行）：

| 进 dom_snapshot/models.py | 留在 TreeWalker/browser/views.py |
|---|---|
| `DOMRect` | `BrowserStateSummary` |
| `EnhancedAXProperty` / `EnhancedAXNode` | `TabInfo` |
| `EnhancedSnapshotNode` | `BrowserEvent` |
| `EnhancedDOMTreeNode` | `DOMInteractedElement` |
| `SimplifiedNode` | |
| `PropagatingBounds` | |
| `SerializedDOMState` | |
| `FileInputInfo` | |
| `NodeType` | |
| `DOMSelectorMap` | |
| `DOMCollectionConfig` / `DOMCollectionMetrics` | |
| `DOMDegradationLevel` | |
| `DEFAULT_INCLUDE_ATTRIBUTES` / `STATIC_ATTRIBUTES` | |
| `filter_dynamic_classes` | |

注意 `DOMInteractedElement`（locator.py 用它做指纹投影）虽然留 TreeWalker，但它 `load_from_enhanced_dom_tree`
读的是 `EnhancedDOMTreeNode`——TreeWalker 端 import dom-snapshot 的 `EnhancedDOMTreeNode` 即可。

### 耦合点 3：对 `cdp_use.CDPClient` 的硬依赖

**TreeWalker 现状**：`dom.py:21` `from cdp_use import CDPClient`

**dom-snapshot 处理**：定义 `CDPLikeClient` Protocol（鸭子类型），库本身用 `TYPE_CHECKING` 引用，
不硬依赖 `cdp-use` 包。调用方传 cdp-use 客户端或任何兼容实现。

```python
# dom_snapshot/_protocol.py
from __future__ import annotations
from typing import Any, Awaitable, Protocol, TYPE_CHECKING, runtime_checkable

if TYPE_CHECKING:
    from cdp_use import CDPClient  # 仅类型检查用，运行时不导入


@runtime_checkable
class CDPLikeClient(Protocol):
    """快照库唯一的外部依赖契约：一个能发 CDP 命令的客户端。

    cdp-use 的 CDPClient 天然符合（client.send.<Domain>.<Method>(params, session_id=)）。
    任何实现此 Protocol 的对象都可传入 build_dom_state。
    """

    def send(
        self,
        domain: str,
        method: str,
        params: dict | None = None,
        *,
        session_id: str | None = None,
    ) -> Awaitable[Any]:
        """发送 CDP 命令，返回 awaitable 的响应字典。"""
        ...
```

> **注意**：实际抽取时需确认 TreeWalker 的 `client.send` 调用形式（是 `client.send.DOM.getDocument(...)` 还是 `client.send("DOM", "getDocument", ...)`）。
> 若是前者（属性链式），Protocol 要调整为暴露各 Domain 的属性对象。这是抽取第一步要核实的细节。

## 四、Public API

```python
# dom_snapshot/__init__.py
from __future__ import annotations
from ._protocol import CDPLikeClient
from .collector import build_dom_state, EMPTY_DOM_STATE
from .models import (
    SerializedDOMState,
    EnhancedDOMTreeNode,
    SimplifiedNode,
    FileInputInfo,
    DOMRect,
    DOMCollectionConfig,
    DOMCollectionMetrics,
    DOMDegradationLevel,
)

__all__ = [
    # 主入口
    "build_dom_state",       # async (client, session_id, prev_map, cfg) -> (SerializedDOMState, DOMCollectionMetrics)
    "EMPTY_DOM_STATE",       # 采集失败的兜底空状态
    # 数据模型
    "SerializedDOMState",    # 含 element_tree_text / selector_map / file_inputs_meta / page_stats
    "EnhancedDOMTreeNode",   # selector_map 的 value 类型（含 xpath/attributes/snapshot_node/ax_node）
    "SimplifiedNode",        # 序列化五步过滤后的简化节点
    "FileInputInfo",         # file_inputs_meta 的元素类型（backend_node_id/accept/visible/upload_ancestor）
    "DOMRect",               # 几何信息
    "DOMCollectionConfig",   # 采集配置
    "DOMCollectionMetrics",  # 采集指标（各源耗时/节点数/降级级别）
    "DOMDegradationLevel",   # 降级级别枚举
    # 协议
    "CDPLikeClient",         # CDP 客户端鸭子类型
]
```

**设计原则**：
- 只暴露 `build_dom_state` 一个函数入口 + 数据模型 + Protocol
- 不暴露内部模块（collector / serializer / paint_order / interactive 是实现细节）
- 调用方不需要了解三源采集或五步过滤，拿到 `SerializedDOMState` 即可

## 五、特殊格式产出位置（给维护者的地图）

LLM 看到的文本树里有几种特殊格式，分散在不同模块。维护时定位用：

| 格式 | 产出位置 | 说明 |
|---|---|---|
| `[index]<tag attr=val /> text` 主格式 | serializer.py `serialize_tree()` | index = backend_node_id |
| `*` 新元素前缀 | serializer.py `serialize_tree()` | 对比 prev_map（上次 selector_map）判定 |
| `\|scroll element\|` 可滚动标记 | serializer.py `serialize_tree()` | 数据来自 `EnhancedDOMTreeNode.should_show_scroll_info` |
| `compound_components=(...)` 复合组件 | serializer.py `_add_compound_components()` + 渲染 | input/select/details/audio/video 的子组件 |
| Shadow DOM 边界 | serializer.py `serialize_tree()` | `Open Shadow` / `Closed Shadow` / `Shadow End` |
| SVG 折叠 | serializer.py `serialize_tree()` | `<svg ... /> <!-- SVG content collapsed -->` |
| `[File Inputs]` 段 | **不在库内**——消费方渲染 | 数据由 `_collect_file_inputs()` 产进 `file_inputs_meta`，渲染在 TreeWalker `prompts/system_prompt.py` |
| `[Page Stats]` 段 | serializer.py `_collect_page_stats()` 产数据 | 渲染同上，在消费方 |

> **库的职责边界**：dom-snapshot 只产 `element_tree_text`（主文本树）+ 结构化数据（selector_map / file_inputs_meta / page_stats）。
> 段级组装（`[Page DOM]` / `[File Inputs]` / `[Page Stats]` 标题 + 拼接）是消费方的事（TreeWalker 在 `build_state_message` 里做）。

## 六、外部依赖

| 依赖 | 必需性 | 用途 |
|---|---|---|
| Python ≥ 3.11 | 必需 | `from __future__ import annotations` / dataclass slots / typing 新特性 |
| `cdp-use` | **运行时可选**（仅类型检查用） | 库用 Protocol 解耦；调用方自己装 cdp-use 并传客户端进来 |
| `pydantic` | **不依赖** | DOM 核心模型全用 dataclass（TreeWalker 的 views.py 混了 pydantic，抽取时剥离） |
| stdlib（hashlib/uuid/asyncio/logging/time/re） | 必需 | 已含 |

**对比 TreeWalker**：TreeWalker 的快照代码拖了 pydantic（聚合状态模型）+ cdp-use（硬依赖）。
dom-snapshot 剥离 pydantic，cdp-use 改 Protocol，最小化外部依赖。

## 七、测试策略

- **单元测试**：三源融合、五步过滤各步、特殊格式产出（用录制的 CDP 响应 fixture，不连真浏览器）
- **快照测试**：固定 CDP 响应 → 固定 element_tree_text（防回归）
- **集成测试**（可选）：连真 Chrome（`--remote-debugging-port`）跑 bilibili，对照 TreeWalker 现有产出
- **抽取等价性验证**：dom-snapshot 产出 vs TreeWalker 原始产出 byte-for-byte 一致（抽取无损的核心判据）

**fixture 来源**：从 TreeWalker 现有测试或 `debug_model_page_view.py` 录制的 CDP 响应 JSON。

## 八、与 TreeWalker / treeforge 的关系

```
                dom-snapshot（本库）
                   ▲           ▲
                   │           │
          pip install    pip install
                   │           │
        TreeWalker │           │ treeforge
        (agent 运行时)        (采集层 P2 + 蒸馏层)
```

- **TreeWalker**：抽取后改为 `from dom_snapshot import build_dom_state`，删本地 5 文件。
  agent 运行时（get_state / build_state_message）行为不变
- **treeforge**：采集层（`treeforge/capture/cdp_session.py`）用轻量 CDP 包装 + dom-snapshot，
  绕开 TreeWalker 的 BrowserSession（3818 行大杂烩）

**抽取的长期价值**：三个工程共享同一份快照实现，避免格式漂移。
任何对快照逻辑的改进（如新的过滤规则、新的特殊格式）一处改、三处受益。
