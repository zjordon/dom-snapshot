"""进阶示例：演示消费方如何消费 SerializedDOMState 的结构化数据。

聚焦三个消费方关心的场景（开箱即跑，复用 hello_snapshot.py 的 FakeClient）：
  1. 降级处理：DOMCollectionMetrics.degradation_level 怎么指导消费方决策
  2. selector_map 元素定位：模型用 [index] 找元素后，怎么读坐标/属性/xpath
  3. is_interactive + iframe target 工具：M2 暴露的 public 工具函数

本例给「写 agent / 写采集层」的人看——dom-snapshot 产出 SerializedDOMState 后，
TreeWalker / treeforge 怎么用这些数据。对比 hello_snapshot.py（看文本树长什么样）。

用法：
    uv run python examples/inspect_dom_state.py
"""

from __future__ import annotations

import asyncio
import os
import sys

# 让本脚本能从同目录导入 hello_snapshot（直接 python 运行时 examples 不是包）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hello_snapshot import FakeClient

from dom_snapshot import (
    DOMDegradationLevel,
    attach_to_iframe_target,
    build_dom_state,
    build_frame_target_map,
)
from dom_snapshot.interactive import is_interactive
from dom_snapshot.models import DOMRect, EnhancedDOMTreeNode, NodeType


def _demo_degradation_decision(actual_level: DOMDegradationLevel) -> None:
    """场景1：消费方根据降级级别调整策略。"""
    print("=" * 70)
    print("[场景1] 降级级别 → 消费方决策")
    print("=" * 70)
    print("dom-snapshot 采集失败不抛异常，而是返回 EMPTY_DOM_STATE + FAILED 级别。")
    print("消费方（如 agent）应据此决定重试 / 提示用户 / 降级继续：\n")

    decision_map = {
        DOMDegradationLevel.FULL: "三源齐全，正常使用 element_tree_text",
        DOMDegradationLevel.PARTIAL: "AX 缺失，无障碍语义不完整但可继续",
        DOMDegradationLevel.MINIMAL: "仅 DOM 树（无布局/可见性），元素可能误判可见性",
        DOMDegradationLevel.FAILED: "DOM 树采集失败 → EMPTY_DOM_STATE，应重试或报错",
    }
    for level in DOMDegradationLevel:
        marker = "  ← 本例实际" if level == actual_level else ""
        print(f"  {level.value:8s} → {decision_map[level]}{marker}")


def _demo_locate_element(selector_map: dict[int, EnhancedDOMTreeNode]) -> None:
    """场景2：模型用 [index] 定位元素后，读坐标/属性/xpath 准备点击。"""
    print("\n" + "=" * 70)
    print("[场景2] selector_map 元素定位（模型决策 click(index=N) 后的消费方动作）")
    print("=" * 70)
    if not selector_map:
        print("  （selector_map 为空，无元素可演示）")
        return

    for idx, node in sorted(selector_map.items()):
        print(f"\n  [{idx}] <{node.tag_name}>")
        print(f"      attributes      = {node.attributes}")
        print(f"      xpath           = {node.xpath!r}")
        print(f"      backend_node_id = {node.backend_node_id}")
        snap = node.snapshot_node
        if snap and snap.bounds:
            b: DOMRect = snap.bounds
            print(
                f"      bounds          = x={b.x:.0f} y={b.y:.0f} w={b.width:.0f} h={b.height:.0f}"
            )
            print(f"      中心点(x,y)     = ({node.x}, {node.y})  ← 点击坐标")
        print(f"      is_interactive  = {is_interactive(node)}  ← 交互检测（编号依据）")


def _demo_interactive_detection() -> None:
    """场景3a：演示 is_interactive 对单个节点的判定（不依赖完整采集）。"""
    print("\n" + "=" * 70)
    print("[场景3a] is_interactive 单独使用（不跑采集也能判定）")
    print("=" * 70)
    cases = [
        (
            "原生交互标签 <button>",
            EnhancedDOMTreeNode(1, 1, NodeType.ELEMENT_NODE, "BUTTON", "", {}),
        ),
        (
            "带 onclick 的 <div>",
            EnhancedDOMTreeNode(2, 2, NodeType.ELEMENT_NODE, "DIV", "", {"onclick": "do()"}),
        ),
        ("纯文本节点", EnhancedDOMTreeNode(3, 3, NodeType.TEXT_NODE, "#text", "hi", {})),
    ]
    for desc, node in cases:
        print(f"  {desc:22s} → is_interactive = {is_interactive(node)}")


async def _demo_iframe_tools(client) -> None:
    """场景3b：演示 M2 提为 public 的 iframe target 工具函数。

    这两个函数（build_frame_target_map / attach_to_iframe_target）原是 dom.py 私有，
    M2 提为 public API 供消费方（如 TreeWalker session.py 的 evaluate(frame=...)）复用——
    进跨源 iframe 执行操作时需 attach 到独立 target。
    """
    print("\n" + "=" * 70)
    print("[场景3b] iframe target 工具（进跨源 iframe 执行操作用）")
    print("=" * 70)

    frame_map, url_map = await build_frame_target_map(client)
    print(f"  build_frame_target_map → frame→target: {frame_map}, url→target: {url_map}")

    sid = await attach_to_iframe_target(client, "target-xxx")
    print(f"  attach_to_iframe_target → sessionId = {sid!r}")
    print("  （真实场景：用此 sessionId 在跨源 iframe 内执行 DOM/Runtime 命令）")


async def main() -> None:
    client = FakeClient()
    dom_state, metrics = await build_dom_state(client, session_id="demo")

    _demo_degradation_decision(metrics.degradation_level)
    _demo_locate_element(dom_state.selector_map)
    _demo_interactive_detection()
    await _demo_iframe_tools(client)


if __name__ == "__main__":
    asyncio.run(main())
