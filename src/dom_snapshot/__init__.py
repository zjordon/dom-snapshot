"""dom-snapshot：CDP 客户端进 → DOM 文本出。

公共库职责单一：从一个符合 ``CDPLikeClient`` Protocol 的 CDP 客户端采集页面，
经三源采集（DOM 树 / Snapshot / Accessibility）+ 五步过滤，产出给 LLM 看的
``[index]<tag attr=val /> text`` 格式文本树（element_tree_text）。

不做 agent 动作执行、不做段级 prompt 组装、不做事件录制/trace/rerun-history、
无状态无持久化——这些是消费方（TreeWalker / treeforge）的职责。

主入口：``build_dom_state``；详见 ARCHITECTURE.md。
"""

from __future__ import annotations

from dom_snapshot._protocol import CDPLikeClient
from dom_snapshot.collector import (
    EMPTY_DOM_STATE,
    attach_to_iframe_target,
    build_dom_state,
    build_frame_target_map,
)
from dom_snapshot.models import (
    DEFAULT_INCLUDE_ATTRIBUTES,
    DYNAMIC_CLASS_PATTERNS,
    STATIC_ATTRIBUTES,
    DOMCollectionConfig,
    DOMCollectionMetrics,
    DOMDegradationLevel,
    DOMRect,
    DOMSelectorMap,
    EnhancedAXNode,
    EnhancedAXProperty,
    EnhancedDOMTreeNode,
    EnhancedSnapshotNode,
    FileInputInfo,
    NodeType,
    PropagatingBounds,
    SerializedDOMState,
    SimplifiedNode,
    filter_dynamic_classes,
)

__version__ = "0.1.0"

__all__ = [
    # 主入口
    "build_dom_state",  # async (client, session_id, prev_map, cfg) -> (SerializedDOMState, DOMCollectionMetrics)
    "EMPTY_DOM_STATE",  # 采集失败的兜底空状态
    # 跨源 iframe target 工具（public，供消费方 session 复用）
    "build_frame_target_map",  # 构建 frameId/url → targetId 映射
    "attach_to_iframe_target",  # attach 到 iframe target，返回 sessionId
    # 数据模型
    "SerializedDOMState",  # 含 element_tree_text / selector_map / file_inputs_meta / page_stats
    "EnhancedDOMTreeNode",  # selector_map 的 value 类型
    "EnhancedSnapshotNode",  # 布局/可见性/坐标数据
    "EnhancedAXNode",  # 语义角色/名称/状态
    "EnhancedAXProperty",  # 单个 AX 属性
    "SimplifiedNode",  # 序列化五步过滤后的简化节点
    "FileInputInfo",  # file_inputs_meta 元素类型
    "DOMRect",  # 几何信息
    "PropagatingBounds",  # 包围盒传播（Step 4 用）
    "NodeType",  # DOM 节点类型枚举
    "DOMSelectorMap",  # dict[int, EnhancedDOMTreeNode]
    "DOMCollectionConfig",  # 采集配置
    "DOMCollectionMetrics",  # 采集指标
    "DOMDegradationLevel",  # 降级级别枚举
    "DEFAULT_INCLUDE_ATTRIBUTES",  # 序列化属性白名单
    "STATIC_ATTRIBUTES",  # 稳定属性集（hash 用）
    "DYNAMIC_CLASS_PATTERNS",  # 动态 class 模式（filter_dynamic_classes 用）
    "filter_dynamic_classes",  # 剥离动态 class
    # 协议
    "CDPLikeClient",  # CDP 客户端鸭子类型
]
