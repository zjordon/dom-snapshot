"""全链路 import 冒烟测试：守护 dom-snapshot 无循环依赖 + public API 完整性。

M2 把 dom.py ↔ serializer.py 的循环依赖打破（interactive.py 独立）后，
本测试验证：
- import dom_snapshot 不触发 CircularImport
- 所有 public API 可访问
- build_dom_state / serializer / collector 可相互 import
- 逐模块 import 无副作用
"""

from __future__ import annotations

import importlib

import dom_snapshot

# ── 无循环依赖 ─────────────────────────────────────────────────────────


def test_import_dom_snapshot_no_circular():
    """顶层 import 不抛 CircularImportError。"""
    # import dom_snapshot 已在模块顶部完成；此处显式 reload 再验证一次
    importlib.reload(dom_snapshot)


def test_all_submodules_importable():
    """8 个内部模块逐一 import 无异常（验证依赖方向无环）。"""
    modules = [
        "dom_snapshot._protocol",
        "dom_snapshot.models",
        "dom_snapshot.cdp_timeout",
        "dom_snapshot.paint_order",
        "dom_snapshot.interactive",
        "dom_snapshot.collector",
        "dom_snapshot.serializer",
    ]
    for mod_name in modules:
        mod = importlib.import_module(mod_name)
        assert mod is not None, f"import {mod_name} 失败"


# ── public API 完整性 ──────────────────────────────────────────────────


def test_public_api_all_accessible():
    """__all__ 中每个名字都能从 dom_snapshot 顶层访问。"""
    assert len(dom_snapshot.__all__) > 0
    for name in dom_snapshot.__all__:
        assert hasattr(dom_snapshot, name), f"public API 缺失: {name}"


def test_core_public_api_present():
    """核心 public API 必须存在（ARCHITECTURE 第四节契约）。"""
    required = {
        # 主入口
        "build_dom_state",
        "EMPTY_DOM_STATE",
        "build_frame_target_map",
        "attach_to_iframe_target",
        # 数据模型
        "SerializedDOMState",
        "EnhancedDOMTreeNode",
        "SimplifiedNode",
        "FileInputInfo",
        "DOMRect",
        "DOMCollectionConfig",
        "DOMCollectionMetrics",
        "DOMDegradationLevel",
        "NodeType",
        # 协议
        "CDPLikeClient",
        # 常量/函数
        "DEFAULT_INCLUDE_ATTRIBUTES",
        "STATIC_ATTRIBUTES",
        "DYNAMIC_CLASS_PATTERNS",
        "filter_dynamic_classes",
    }
    for name in required:
        assert name in dom_snapshot.__all__, f"{name} 未在 __all__ 中导出"
        assert hasattr(dom_snapshot, name), f"{name} 不可访问"


# ── 关键入口可调用 ────────────────────────────────────────────────────


def test_build_dom_state_is_callable():
    assert callable(dom_snapshot.build_dom_state)


def test_build_frame_target_map_is_callable():
    assert callable(dom_snapshot.build_frame_target_map)


def test_attach_to_iframe_target_is_callable():
    assert callable(dom_snapshot.attach_to_iframe_target)


def test_empty_dom_state_is_serialized_state():
    from dom_snapshot.models import SerializedDOMState

    assert isinstance(dom_snapshot.EMPTY_DOM_STATE, SerializedDOMState)
    assert dom_snapshot.EMPTY_DOM_STATE.element_tree_text == ""
    assert dom_snapshot.EMPTY_DOM_STATE.selector_map == {}


def test_version_string():
    assert isinstance(dom_snapshot.__version__, str)
    assert dom_snapshot.__version__
