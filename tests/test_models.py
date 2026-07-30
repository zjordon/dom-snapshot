"""models.py 单元测试：数据模型构造 + filter_dynamic_classes + EnhancedDOMTreeNode 的
hash/xpath/compute_stable_hash（DOMInteractedElement.load_from_enhanced_dom_tree 间接读的字段）。

这些字段在 M2.1 核实中被标记为"必须随 EnhancedDOMTreeNode 进 dom-snapshot"，遗漏会导致
消费方（TreeWalker DOMInteractedElement）运行时 AttributeError。本测试守护字段完整性。
"""

from __future__ import annotations

from dom_snapshot.models import (
    DEFAULT_INCLUDE_ATTRIBUTES,
    DYNAMIC_CLASS_PATTERNS,
    STATIC_ATTRIBUTES,
    DOMRect,
    EnhancedAXNode,
    EnhancedDOMTreeNode,
    EnhancedSnapshotNode,
    FileInputInfo,
    NodeType,
    SerializedDOMState,
    SimplifiedNode,
    filter_dynamic_classes,
)

# ── DOMRect ────────────────────────────────────────────────────────────


def test_dom_rect_to_dict():
    r = DOMRect(1.0, 2.0, 3.0, 4.0)
    assert r.to_dict() == {"x": 1.0, "y": 2.0, "width": 3.0, "height": 4.0}
    assert r.__json__() == r.to_dict()


# ── filter_dynamic_classes + DYNAMIC_CLASS_PATTERNS ───────────────────


def test_filter_dynamic_classes_strips_dynamic_keeps_semantic():
    # focus/active 是动态模式（剥离），btn/btn-primary 是语义（保留，排序）
    assert filter_dynamic_classes("btn focus active btn-primary") == "btn btn-primary"


def test_filter_dynamic_classes_empty_and_none():
    assert filter_dynamic_classes("") == ""
    assert filter_dynamic_classes(None) == ""


def test_filter_dynamic_classes_all_dynamic_yields_empty():
    # 全是动态类 → 全剥离 → 空串
    assert filter_dynamic_classes("hover focus active") == ""


def test_dynamic_class_patterns_is_frozenset_and_nonempty():
    assert isinstance(DYNAMIC_CLASS_PATTERNS, frozenset)
    assert len(DYNAMIC_CLASS_PATTERNS) > 0
    # 关键模式必须在内（compute_stable_hash 依赖）
    assert "focus" in DYNAMIC_CLASS_PATTERNS
    assert "hover" in DYNAMIC_CLASS_PATTERNS


# ── 常量集合完整性 ────────────────────────────────────────────────────


def test_static_attributes_contains_identifying_keys():
    # compute_stable_hash / __hash__ 按 STATIC_ATTRIBUTES 过滤，这些键必须在
    for key in ("class", "id", "role", "data-testid"):
        assert key in STATIC_ATTRIBUTES


def test_default_include_attributes_contains_core_keys():
    # serializer 白名单必须有这些（_build_attributes_string 依赖）
    for key in ("role", "value", "placeholder", "aria-label", "name"):
        assert key in DEFAULT_INCLUDE_ATTRIBUTES


# ── NodeType 枚举 ──────────────────────────────────────────────────────


def test_node_type_values():
    assert NodeType.ELEMENT_NODE.value == 1
    assert NodeType.TEXT_NODE.value == 3
    assert NodeType.DOCUMENT_NODE.value == 9
    assert NodeType.DOCUMENT_FRAGMENT_NODE.value == 11


def test_node_type_is_constructible_from_int():
    # collector._construct_enhanced_node 用 NodeType(node_type_val) 构造
    assert NodeType(1) is NodeType.ELEMENT_NODE
    assert NodeType(3) is NodeType.TEXT_NODE


# ── EnhancedDOMTreeNode 核心字段 + DOMInteractedElement 依赖的方法 ─────


def _make_node(
    node_id: int = 1,
    backend_node_id: int = 100,
    node_type: NodeType = NodeType.ELEMENT_NODE,
    node_name: str = "DIV",
    attributes: dict[str, str] | None = None,
    **kwargs,
) -> EnhancedDOMTreeNode:
    return EnhancedDOMTreeNode(
        node_id=node_id,
        backend_node_id=backend_node_id,
        node_type=node_type,
        node_name=node_name,
        node_value="",
        attributes=attributes or {},
        **kwargs,
    )


def test_enhanced_node_required_fields():
    n = _make_node()
    assert n.node_id == 1
    assert n.backend_node_id == 100
    assert n.node_type is NodeType.ELEMENT_NODE
    assert n.tag_name == "div"


def test_enhanced_node_tag_name_lowercases_node_name():
    assert _make_node(node_name="BUTTON").tag_name == "button"
    assert _make_node(node_name="A").tag_name == "a"


def test_enhanced_node_uuid_auto_generated():
    n1, n2 = _make_node(), _make_node()
    assert n1.uuid != n2.uuid
    assert len(n1.uuid) > 0


def test_enhanced_node_xpath_single_element():
    # 无父节点 → xpath 是单 tag
    n = _make_node(node_name="div")
    assert n.xpath == "div"


def test_enhanced_node_xpath_with_parent_chain():
    parent = _make_node(node_id=1, node_name="body")
    child = _make_node(node_id=2, node_name="div")
    child.parent_node = parent
    assert child.xpath == "body/div"


def test_enhanced_node_hash_stable_for_same_content():
    # 同样字段（含 parent 链 + static attrs + ax_name）→ 同 hash
    parent = _make_node(node_id=1, node_name="body")
    attrs = {"class": "btn", "id": "x"}
    n1 = _make_node(node_id=2, node_name="div", attributes=attrs)
    n1.parent_node = parent
    n2 = _make_node(node_id=99, node_name="div", attributes=attrs)
    n2.parent_node = parent
    # node_id 不同但 hash 基于路径+静态属性，应一致
    assert hash(n1) == hash(n2)


def test_enhanced_node_hash_differs_with_different_ax_name():
    parent = _make_node(node_id=1, node_name="body")
    n1 = _make_node(node_id=2, node_name="div")
    n1.parent_node = parent
    n2 = _make_node(node_id=2, node_name="div")
    n2.parent_node = parent
    n2.ax_node = EnhancedAXNode(
        ax_node_id="ax1",
        ignored=False,
        role=None,
        name="Submit",
        description=None,
        properties=None,
        child_ids=None,
    )
    assert hash(n1) != hash(n2)


def test_enhanced_node_compute_stable_hash_returns_int():
    n = _make_node(attributes={"class": "btn focus", "id": "x"})
    h = n.compute_stable_hash()
    assert isinstance(h, int)
    # 动态 class 'focus' 应被剥离（filter_dynamic_classes），但 id 保留 → 非零 hash


def test_enhanced_node_compute_stable_hash_strips_dynamic_class():
    # 动态类不影响 stable hash
    n_static = _make_node(attributes={"class": "btn", "id": "x"})
    n_dynamic = _make_node(attributes={"class": "btn focus hover", "id": "x"})
    assert n_static.compute_stable_hash() == n_dynamic.compute_stable_hash()


def test_enhanced_node_element_hash_property_matches_hash():
    n = _make_node()
    assert n.element_hash == hash(n)


def test_enhanced_node_json_serializable():
    n = _make_node(attributes={"id": "x"})
    j = n.__json__()
    assert j["backend_node_id"] == 100
    assert j["node_name"] == "DIV"
    assert j["attributes"] == {"id": "x"}


def test_enhanced_node_children_and_shadow_roots():
    n = _make_node()
    child = _make_node(node_id=2, node_name="span")
    shadow = _make_node(node_id=3, node_name="#shadow-root")
    n.children_nodes = [child]
    n.shadow_roots = [shadow]
    combined = n.children_and_shadow_roots
    assert child in combined
    assert shadow in combined


def test_get_all_children_text():
    root = _make_node(node_id=1, node_name="div")
    t1 = EnhancedDOMTreeNode(2, 102, NodeType.TEXT_NODE, "#text", "Hello", {})
    t2 = EnhancedDOMTreeNode(3, 103, NodeType.TEXT_NODE, "#text", "World", {})
    inner = _make_node(node_id=4, node_name="span")
    inner.children_nodes = [t2]
    root.children_nodes = [t1, inner]
    text = root.get_all_children_text()
    assert "Hello" in text
    assert "World" in text


def test_load_from_enhanced_dom_tree_fields_all_present():
    """DOMInteractedElement.load_from_enhanced_dom_tree 读的 9 个直接字段必须都在。

    本库不迁 DOMInteractedElement（留 TreeWalker），但它读的 EnhancedDOMTreeNode
    字段必须完整保留。这里直接断言这些字段可读，防回归。
    """
    bounds = DOMRect(10, 20, 30, 40)
    snap = EnhancedSnapshotNode(
        is_clickable=True,
        cursor_style="pointer",
        bounds=bounds,
        clientRects=None,
        scrollRects=None,
        computed_styles=None,
        paint_order=1,
        stacking_contexts=None,
    )
    ax = EnhancedAXNode(
        ax_node_id="ax1",
        ignored=False,
        role="button",
        name="Submit",
        description=None,
        properties=None,
        child_ids=None,
    )
    n = EnhancedDOMTreeNode(
        node_id=5,
        backend_node_id=555,
        node_type=NodeType.ELEMENT_NODE,
        node_name="BUTTON",
        node_value="",
        attributes={"id": "go"},
        frame_id="F1",
        ax_node=ax,
        snapshot_node=snap,
    )
    # DOMInteractedElement 直接读的字段
    assert n.node_id == 5
    assert n.backend_node_id == 555
    assert n.frame_id == "F1"
    assert n.node_type is NodeType.ELEMENT_NODE
    assert n.node_value == ""
    assert n.node_name == "BUTTON"
    assert n.attributes == {"id": "go"}
    assert n.ax_node.name == "Submit"
    assert n.snapshot_node.bounds == bounds
    # 间接读
    assert n.xpath == "button"
    assert isinstance(hash(n), int)
    assert isinstance(n.compute_stable_hash(), int)


# ── SimplifiedNode / SerializedDOMState / FileInputInfo ───────────────


def test_simplified_node_defaults():
    n = _make_node()
    sn = SimplifiedNode(original_node=n, children=[])
    assert sn.should_display is True
    assert sn.is_interactive is False
    assert sn.highlight_index is None


def test_serialized_dom_state_defaults():
    state = SerializedDOMState(_root=None, selector_map={}, element_tree_text="x")
    assert state.file_input_backend_ids == []
    assert state.file_inputs_meta == []
    assert state.page_stats == {}


def test_serialized_dom_state_llm_representation():
    # _root=None → 永远返回 Empty DOM 提示（源码：if not self._root 优先）
    empty = SerializedDOMState(_root=None, selector_map={}, element_tree_text="")
    assert "Empty DOM tree" in empty.llm_representation()
    # 有 _root 时返回 element_tree_text
    root_sn = SimplifiedNode(original_node=_make_node(), children=[])
    filled = SerializedDOMState(_root=root_sn, selector_map={}, element_tree_text="[1]<a/>")
    assert filled.llm_representation() == "[1]<a/>"


def test_file_input_info_defaults():
    fi = FileInputInfo(backend_node_id=42)
    assert fi.accept == ""
    assert fi.visible is True
    assert fi.upload_ancestor is False
    assert fi.class_name == ""
