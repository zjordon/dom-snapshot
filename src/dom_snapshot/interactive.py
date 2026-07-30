"""可交互元素检测：判断 DOM 节点是否可被点击/操作（编号用）。

从 TreeWalker dom.py 抽出，独立成模块以打破 collector ↔ serializer 循环依赖：
collector.py 和 serializer.py 都从此导入 is_interactive，不再互相懒导入。

检测逻辑：14 条规则决策瀑布（ClickableElementDetector.is_interactive），
综合 JS 点击监听器 / AX 角色 / HTML 标签 / cursor:pointer / 搜索关键词等信号，
命中即短路返回。is_interactive 是供序列化 Step 5 编号使用的公开入口。
"""

from __future__ import annotations

from dom_snapshot.models import EnhancedDOMTreeNode, NodeType


class ClickableElementDetector:
    """14 条规则决策瀑布，检测 DOM 元素是否可交互。

    规则按信号强度排序，命中即短路返回。
    """

    @staticmethod
    def is_interactive(node: EnhancedDOMTreeNode) -> bool:
        def has_form_control_descendant(element: EnhancedDOMTreeNode, max_depth: int = 2) -> bool:
            if max_depth <= 0:
                return False
            for child in element.children_and_shadow_roots:
                if child.node_type != NodeType.ELEMENT_NODE:
                    continue
                if child.tag_name in {"input", "select", "textarea"}:
                    return True
                if has_form_control_descendant(child, max_depth=max_depth - 1):
                    return True
            return False

        # 规则 1: 节点类型守卫 — 只有 ELEMENT_NODE 才可能交互
        if node.node_type != NodeType.ELEMENT_NODE:
            return False

        # 规则 2: html/body 排除 — 文档结构元素不是交互目标
        if node.tag_name in {"html", "body"}:
            return False

        # 规则 3: JS 点击监听器 — 最强信号（Vue @click, React onClick, Angular (click), 原生 addEventListener）
        if node.has_js_click_listener:
            return True

        # 规则 4: IFRAME/FRAME — 大尺寸 iframe 可能有可滚动内容
        if node.tag_name in {"iframe", "frame"}:
            if node.snapshot_node and node.snapshot_node.bounds:
                if node.snapshot_node.bounds.width > 100 and node.snapshot_node.bounds.height > 100:
                    return True

        # 规则 5: Label 处理 — 避免双重激活
        if node.tag_name == "label":
            if node.attributes and node.attributes.get("for"):
                return False
            if has_form_control_descendant(node, max_depth=2):
                return True
            # 其他 label 继续后续规则

        # 规则 6: Span 包装器 — 检测包裹表单控件的 span
        if node.tag_name == "span":
            if has_form_control_descendant(node, max_depth=2):
                return True
            # 其他 span 继续后续规则

        # 规则 7: 搜索元素检测 — class/id/data-* 含搜索关键词
        if node.attributes:
            search_indicators = {
                "search",
                "magnify",
                "glass",
                "lookup",
                "find",
                "query",
                "search-icon",
                "search-btn",
                "search-button",
                "searchbox",
            }
            class_list = node.attributes.get("class", "").lower().split()
            if any(indicator in " ".join(class_list) for indicator in search_indicators):
                return True
            element_id = node.attributes.get("id", "").lower()
            if any(indicator in element_id for indicator in search_indicators):
                return True
            for attr_name, attr_value in node.attributes.items():
                if attr_name.startswith("data-") and any(
                    indicator in attr_value.lower() for indicator in search_indicators
                ):
                    return True

        # 规则 8: AX 属性检查 — 可访问性树属性
        if node.ax_node and node.ax_node.properties:
            for prop in node.ax_node.properties:
                try:
                    if prop.name == "disabled" and prop.value:
                        return False
                    if prop.name == "hidden" and prop.value:
                        return False
                    if prop.name in ("focusable", "editable", "settable") and prop.value:
                        return True
                    if prop.name in ("checked", "expanded", "pressed", "selected"):
                        return True
                    if prop.name in ("required", "autocomplete") and prop.value:
                        return True
                    if prop.name == "keyshortcuts" and prop.value:
                        return True
                except (AttributeError, ValueError):
                    continue

        # 规则 9: 交互标签 — 原生 HTML 交互元素
        interactive_tags = {
            "button",
            "input",
            "select",
            "textarea",
            "a",
            "details",
            "summary",
            "option",
            "optgroup",
        }
        if node.tag_name in interactive_tags:
            return True

        # 规则 10: 交互 HTML 属性 — 内联事件处理器和 tabindex
        if node.attributes:
            interactive_attributes = {
                "onclick",
                "onmousedown",
                "onmouseup",
                "onkeydown",
                "onkeyup",
                "tabindex",
            }
            if any(attr in node.attributes for attr in interactive_attributes):
                return True

            # 规则 11: ARIA role（HTML 属性）
            if "role" in node.attributes:
                interactive_roles = {
                    "button",
                    "link",
                    "menuitem",
                    "option",
                    "radio",
                    "checkbox",
                    "tab",
                    "textbox",
                    "combobox",
                    "slider",
                    "spinbutton",
                    "search",
                    "searchbox",
                    "row",
                    "cell",
                    "gridcell",
                }
                if node.attributes["role"] in interactive_roles:
                    return True

        # 规则 12: AX 树 role
        if node.ax_node and node.ax_node.role:
            interactive_ax_roles = {
                "button",
                "link",
                "menuitem",
                "option",
                "radio",
                "checkbox",
                "tab",
                "textbox",
                "combobox",
                "slider",
                "spinbutton",
                "listbox",
                "search",
                "searchbox",
                "row",
                "cell",
                "gridcell",
            }
            if node.ax_node.role in interactive_ax_roles:
                return True

        # 规则 13: 图标尺寸元素 — 10-50px + 有交互属性
        if (
            node.snapshot_node
            and node.snapshot_node.bounds
            and 10 <= node.snapshot_node.bounds.width <= 50
            and 10 <= node.snapshot_node.bounds.height <= 50
        ):
            if node.attributes:
                icon_attributes = {"class", "role", "onclick", "data-action", "aria-label"}
                if any(attr in node.attributes for attr in icon_attributes):
                    return True

        # 规则 14: cursor: pointer — 最终兜底
        if (
            node.snapshot_node
            and node.snapshot_node.cursor_style
            and node.snapshot_node.cursor_style == "pointer"
        ):
            return True

        return False


def is_interactive(node: EnhancedDOMTreeNode) -> bool:
    """公开的交互检测函数，供 DOMTreeSerializer 使用。"""
    return ClickableElementDetector.is_interactive(node)
