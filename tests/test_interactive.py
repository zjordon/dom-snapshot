"""interactive.py 单元测试：14 条交互检测规则的关键路径 + 边界。

is_interactive 是序列化 Step 5 编号的核心判定。测试覆盖：
- 规则 1（节点类型守卫）/ 规则 2（html/body 排除）
- 规则 3（JS click listener）/ 规则 9（原生交互标签）
- 规则 8（AX 属性）/ 规则 12（AX role）
- 规则 10/11（HTML 属性 / ARIA role）/ 规则 14（cursor:pointer）
- 规则 5（label）/ 规则 4（iframe 尺寸）

从 dom.py 抽出后逻辑零改动，本测试守护等价性。
"""

from __future__ import annotations

import pytest

from dom_snapshot.interactive import ClickableElementDetector, is_interactive
from dom_snapshot.models import (
    DOMRect,
    EnhancedAXNode,
    EnhancedAXProperty,
    EnhancedDOMTreeNode,
    EnhancedSnapshotNode,
    NodeType,
)


def _node(
    node_type: NodeType = NodeType.ELEMENT_NODE,
    node_name: str = "DIV",
    attributes: dict[str, str] | None = None,
    *,
    ax_node: EnhancedAXNode | None = None,
    snapshot_node: EnhancedSnapshotNode | None = None,
    has_js_click_listener: bool = False,
    children: list[EnhancedDOMTreeNode] | None = None,
) -> EnhancedDOMTreeNode:
    n = EnhancedDOMTreeNode(
        node_id=1,
        backend_node_id=100,
        node_type=node_type,
        node_name=node_name,
        node_value="",
        attributes=attributes or {},
        ax_node=ax_node,
        snapshot_node=snapshot_node,
        has_js_click_listener=has_js_click_listener,
    )
    if children is not None:
        n.children_nodes = children
    return n


def _bounds(w: float, h: float) -> DOMRect:
    return DOMRect(0.0, 0.0, w, h)


def _snap(bounds: DOMRect | None = None, cursor: str | None = None) -> EnhancedSnapshotNode:
    return EnhancedSnapshotNode(
        is_clickable=None,
        cursor_style=cursor,
        bounds=bounds,
        clientRects=None,
        scrollRects=None,
        computed_styles=None,
        paint_order=None,
        stacking_contexts=None,
    )


def _ax(
    role: str | None = None, name: str | None = None, props: list | None = None
) -> EnhancedAXNode:
    return EnhancedAXNode(
        ax_node_id="ax1",
        ignored=False,
        role=role,
        name=name,
        description=None,
        properties=props,
        child_ids=None,
    )


# is_interactive 是 ClickableElementDetector.is_interactive 的薄封装
def test_is_interactive_delegates_to_detector():
    n = _node(node_name="a")
    assert is_interactive(n) == ClickableElementDetector.is_interactive(n)


# ── 规则 1：节点类型守卫 ───────────────────────────────────────────────


def test_rule1_text_node_not_interactive():
    assert is_interactive(_node(node_type=NodeType.TEXT_NODE, node_name="#text")) is False


def test_rule1_document_node_not_interactive():
    assert is_interactive(_node(node_type=NodeType.DOCUMENT_NODE, node_name="#document")) is False


# ── 规则 2：html/body 排除 ─────────────────────────────────────────────


def test_rule2_html_excluded():
    assert is_interactive(_node(node_name="HTML")) is False


def test_rule2_body_excluded():
    assert is_interactive(_node(node_name="BODY")) is False


# ── 规则 3：JS 点击监听器（最强信号）──────────────────────────────────


def test_rule3_js_click_listener_makes_interactive():
    n = _node(node_name="div", has_js_click_listener=True)
    assert is_interactive(n) is True


# ── 规则 4：iframe 尺寸 ────────────────────────────────────────────────


def test_rule4_large_iframe_interactive():
    n = _node(node_name="IFRAME", snapshot_node=_snap(_bounds(200, 200)))
    assert is_interactive(n) is True


def test_rule4_small_iframe_not_interactive():
    n = _node(node_name="IFRAME", snapshot_node=_snap(_bounds(50, 50)))
    assert is_interactive(n) is False


def test_rule4_iframe_without_bounds_not_interactive():
    n = _node(node_name="IFRAME")
    assert is_interactive(n) is False


# ── 规则 5：label ──────────────────────────────────────────────────────


def test_rule5_label_with_for_not_interactive():
    # <label for="x"> 不应交互（避免双重激活）
    n = _node(node_name="LABEL", attributes={"for": "username"})
    assert is_interactive(n) is False


def test_rule5_label_wrapping_input_interactive():
    inner = _node(node_name="input", attributes={"type": "text"})
    label = _node(node_name="LABEL", children=[inner])
    assert is_interactive(label) is True


# ── 规则 6：span 包装器 ────────────────────────────────────────────────


def test_rule6_span_wrapping_input_interactive():
    inner = _node(node_name="input")
    span = _node(node_name="SPAN", children=[inner])
    assert is_interactive(span) is True


def test_rule6_plain_span_not_interactive():
    span = _node(node_name="SPAN")
    assert is_interactive(span) is False


# ── 规则 8：AX 属性 ────────────────────────────────────────────────────


def test_rule8_ax_focusable_interactive():
    props = [EnhancedAXProperty(name="focusable", value=True)]
    n = _node(node_name="div", ax_node=_ax(props=props))
    assert is_interactive(n) is True


def test_rule8_ax_disabled_not_interactive():
    props = [EnhancedAXProperty(name="disabled", value=True)]
    n = _node(node_name="button", ax_node=_ax(props=props))
    assert is_interactive(n) is False


def test_rule8_ax_hidden_not_interactive():
    props = [EnhancedAXProperty(name="hidden", value=True)]
    n = _node(node_name="div", ax_node=_ax(props=props))
    assert is_interactive(n) is False


# ── 规则 9：原生交互标签 ───────────────────────────────────────────────


@pytest.mark.parametrize(
    "tag", ["button", "input", "select", "textarea", "a", "details", "summary"]
)
def test_rule9_native_interactive_tags(tag: str):
    assert is_interactive(_node(node_name=tag.upper())) is True


# ── 规则 10：内联事件属性 ─────────────────────────────────────────────


def test_rule10_onclick_attribute_interactive():
    n = _node(node_name="div", attributes={"onclick": "doSomething()"})
    assert is_interactive(n) is True


def test_rule10_tabindex_interactive():
    n = _node(node_name="div", attributes={"tabindex": "0"})
    assert is_interactive(n) is True


# ── 规则 11：ARIA role（HTML 属性）────────────────────────────────────


def test_rule11_aria_role_button_interactive():
    n = _node(node_name="div", attributes={"role": "button"})
    assert is_interactive(n) is True


def test_rule11_aria_role_noninteractive_not_interactive():
    n = _node(node_name="div", attributes={"role": "heading"})
    assert is_interactive(n) is False


# ── 规则 12：AX 树 role ────────────────────────────────────────────────


def test_rule12_ax_role_link_interactive():
    n = _node(node_name="div", ax_node=_ax(role="link"))
    assert is_interactive(n) is True


def test_rule12_ax_role_heading_not_interactive():
    n = _node(node_name="div", ax_node=_ax(role="heading"))
    assert is_interactive(n) is False


# ── 规则 13：图标尺寸 + 交互属性 ─────────────────────────────────────


def test_rule13_icon_sized_with_class_interactive():
    # 10-50px + 有交互属性（class）
    n = _node(node_name="i", attributes={"class": "icon"}, snapshot_node=_snap(_bounds(24, 24)))
    assert is_interactive(n) is True


def test_rule13_icon_sized_without_attrs_not_interactive():
    n = _node(node_name="i", snapshot_node=_snap(_bounds(24, 24)))
    assert is_interactive(n) is False


# ── 规则 14：cursor:pointer 兜底 ──────────────────────────────────────


def test_rule14_cursor_pointer_interactive():
    n = _node(node_name="div", snapshot_node=_snap(cursor="pointer"))
    assert is_interactive(n) is True


def test_rule14_cursor_default_not_interactive():
    n = _node(node_name="div", snapshot_node=_snap(cursor="default"))
    assert is_interactive(n) is False


# ── 综合兜底 ───────────────────────────────────────────────────────────


def test_plain_div_no_signals_not_interactive():
    # 无任何交互信号的普通 div → False
    assert is_interactive(_node(node_name="div")) is False
