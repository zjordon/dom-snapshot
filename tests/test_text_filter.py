"""issue #1 修复回归测试：单字符文本节点的过滤行为。

背景：原 `len(text.strip()) > 1` 过滤器误杀个位数表格数值（qty 列 4/3/3/2/2
整体消失，WebArena 评测判 0）。修复后语义（_is_meaningful_text）：
多字符一律保留；单字符仅保留字母/数字（含 CJK）；装饰符（•、|、·）仍滤。

本测试同时覆盖建树（Step 1）与渲染（serialize_tree）两道门——断言最终
element_tree_text，任一道门回退旧条件都会失败。
"""

from __future__ import annotations

from dom_snapshot.models import (
    DOMRect,
    EnhancedDOMTreeNode,
    EnhancedSnapshotNode,
    NodeType,
)
from dom_snapshot.serializer import DOMTreeSerializer, _is_meaningful_text

_VISIBLE_SNAP = EnhancedSnapshotNode(
    is_clickable=None,
    cursor_style=None,
    bounds=DOMRect(0.0, 0.0, 10.0, 10.0),
    clientRects=None,
    scrollRects=None,
    computed_styles={"display": "block", "visibility": "visible"},
    paint_order=1,
    stacking_contexts=None,
)


def _visible_node(
    node_id: int, bid: int, node_type: NodeType, name: str, value: str
) -> EnhancedDOMTreeNode:
    """构造带可见 snapshot 数据的节点（模拟采集完成后的可见元素/文本）。"""
    n = EnhancedDOMTreeNode(
        node_id=node_id,
        backend_node_id=bid,
        node_type=node_type,
        node_name=name,
        node_value=value,
        attributes={},
    )
    n.snapshot_node = _VISIBLE_SNAP
    n.is_visible = True
    return n


def _td_with_text(node_id: int, bid: int, text: str) -> EnhancedDOMTreeNode:
    """模拟报表单元格：可见 <td> 内裸文本子节点（前后空白，同 Magento 现场 DOM）。"""
    td = _visible_node(node_id, bid, NodeType.ELEMENT_NODE, "TD", "")
    text_node = _visible_node(node_id + 1, bid + 1, NodeType.TEXT_NODE, "#text", text)
    td.children_nodes = [text_node]
    return td


def _serialize_cell_texts(*texts: str) -> list[str]:
    """把若干裸文本单元格序列化，返回文本树中的非空文本行（strip 后）。"""
    root = EnhancedDOMTreeNode(1, 1, NodeType.DOCUMENT_NODE, "#document", "", {})
    body = _visible_node(2, 2, NodeType.ELEMENT_NODE, "BODY", "")
    root.children_nodes = [body]
    body.children_nodes = [_td_with_text(10 + i * 2, 100 + i * 2, t) for i, t in enumerate(texts)]
    state, _ = DOMTreeSerializer(root_node=root).serialize_accessible_elements()
    return [ln.strip() for ln in state.element_tree_text.splitlines() if ln.strip()]


# ── 1. 谓词单元级：边界行为逐行断言 ────────────────────────────────────


def test_predicate_single_digits_are_meaningful():
    for d in "0123456789":
        assert _is_meaningful_text(f"  {d}  ") is True  # 前后空白应被 strip


def test_predicate_single_letters_and_cjk_are_meaningful():
    for s in ("M", "L", "S", "男", "女", "中"):
        assert _is_meaningful_text(s) is True


def test_predicate_decorative_single_chars_still_filtered():
    for s in ("•", "|", "·", "-", "$", "。"):
        assert _is_meaningful_text(s) is False


def test_predicate_empty_and_whitespace_filtered():
    for s in ("", "   ", "\n\t "):
        assert _is_meaningful_text(s) is False


def test_predicate_multi_char_always_meaningful():
    for s in ("14", "Total", "ab", "$14.00", "2023"):
        assert _is_meaningful_text(s) is True


# ── 2. 端到端：个位数保留（issue #1 主场景）─────────────────────────


def test_single_digit_qty_values_preserved():
    """Magento Bestsellers qty 列 4/3/3/2/2 场景（issue #1 现场值）。"""
    lines = _serialize_cell_texts(
        "\n        4        \n",
        "\n        3        \n",
        "\n        3        \n",
        "\n        2        \n",
        "\n        2        \n",
    )
    for qty in ("4", "3", "2"):
        assert qty in lines, f"个位数 {qty} 未出现在文本树: {lines}"


def test_zero_preserved():
    """qty=0 也不能丢（原 bug 同样误杀 0）。"""
    assert "0" in _serialize_cell_texts("\n   0   \n")


def test_single_letter_and_cjk_preserved():
    lines = _serialize_cell_texts("M", "男")
    assert "M" in lines
    assert "男" in lines


# ── 3. 端到端：噪声仍滤 + 多字符不变（防回归锚点）────────────────────


def test_decorative_single_char_still_dropped_end_to_end():
    lines = _serialize_cell_texts("•", "|", "·")
    assert lines == [], f"装饰单字符应全部被滤，实际: {lines}"


def test_whitespace_only_text_dropped():
    assert _serialize_cell_texts("   ", "\n\t") == []


def test_multi_char_text_unchanged():
    lines = _serialize_cell_texts("\n        14        \n", "\n        Total        \n")
    assert "14" in lines
    assert "Total" in lines


def test_mixed_column_matches_issue_evidence():
    """issue #1 证据链复刻：同表多位数/商品名保留、个位数（修复后）也保留。"""
    lines = _serialize_cell_texts(
        "\n   4   \n",  # qty（len 1，改前丢）
        "\n   14   \n",  # tfoot 合计（len 2，一直保留）
        "\n   Total   \n",  # 标签（多字符）
        "\n   $14.00   \n",  # 金额（len 5）
    )
    for expected in ("4", "14", "Total", "$14.00"):
        assert expected in lines, f"{expected} 缺失: {lines}"
