"""最小可用示例：用假 CDP 客户端跑通 build_dom_state，开箱即跑（无需 Chrome）。

演示 dom-snapshot 的核心契约：「CDP 客户端进 → DOM 文本出」。
本脚本不连真浏览器，自己构造一个符合 ``CDPLikeClient`` Protocol 的假客户端，
并提供布局数据让元素可见，直观看到三源采集 + 五步过滤产出的文本树格式。

对比 snapshot_live_page.py（连真 Chrome）。想看真实网页快照用那个。

用法：
    uv run python examples/hello_snapshot.py
"""

from __future__ import annotations

import asyncio

from dom_snapshot import (
    CDPLikeClient,  # 仅用于类型注解；cdp-use 的 CDPClient 天然符合此 Protocol
    build_dom_state,
)

# 本例模拟的页面 DOM：
#   <html><body>
#     <a href="/login">登录</a>
#     <input type="text" placeholder="搜索"/>
#     <input type="file" accept="image/*"/>      ← 会被收进 file_inputs_meta
#   </body></html>
#
# 给每个元素配可见的布局数据（display:block + bounds），五步过滤才会保留它们。

# backendNodeId → (x, y, w, h) 布局，让元素通过可见性判定
_LAYOUT = {
    2: (0, 0, 1280, 800),  # html
    3: (0, 0, 1280, 800),  # body
    100: (10, 10, 80, 20),  # a
    200: (10, 40, 200, 30),  # input text
    300: (10, 80, 200, 30),  # input file
}


def _snapshot_response() -> dict:
    """构造 DOMSnapshot.captureSnapshot 的响应（让 _build_snapshot_lookup 能解析）。"""
    bids = sorted(_LAYOUT)
    bounds = [list(_LAYOUT[b]) for b in bids]
    # computedStyles 是稀疏索引表：每行对应一个 layout 节点，每列对应 REQUIRED_COMPUTED_STYLES
    # 顺序：display/visibility/opacity/cursor/pointer-events/overflow/overflow-x/overflow-y/position/background-color
    # 字符串池索引：0=block, 1=visible, 2=1, 3=auto, 4=static, 5=rgba(0,0,0,0)
    strings = ["block", "visible", "1", "auto", "static", "rgba(0, 0, 0, 0)"]
    # 每个节点：display=block(0), visibility=visible(1), opacity=1(2), 其余 auto/static
    styles = [[0, 1, 2, 3, 3, 3, 3, 3, 4, 5] for _ in bids]
    return {
        "documents": [
            {
                "nodes": {"backendNodeId": bids},
                "layout": {
                    "nodeIndex": list(range(len(bids))),
                    "bounds": bounds,
                    "styles": styles,
                    "paintOrders": list(range(len(bids))),
                    "clientRects": bounds,
                    "scrollRects": [[0, 0, 0, 0] for _ in bids],
                },
            }
        ],
        "strings": strings,
    }


# DOM 树（backendNodeId 与 _LAYOUT 对应）
_DOM_TREE = {
    "root": {
        "nodeId": 1,
        "backendNodeId": 1,
        "nodeType": 9,
        "nodeName": "#document",
        "children": [
            {
                "nodeId": 2,
                "backendNodeId": 2,
                "nodeType": 1,
                "nodeName": "html",
                "frameId": "main",
                "children": [
                    {
                        "nodeId": 3,
                        "backendNodeId": 3,
                        "nodeType": 1,
                        "nodeName": "body",
                        "children": [
                            {
                                "nodeId": 10,
                                "backendNodeId": 100,
                                "nodeType": 1,
                                "nodeName": "A",
                                "attributes": ["href", "/login"],
                                "children": [
                                    {
                                        "nodeId": 11,
                                        "backendNodeId": 101,
                                        "nodeType": 3,
                                        "nodeName": "#text",
                                        "nodeValue": "登录",
                                    }
                                ],
                            },
                            {
                                "nodeId": 20,
                                "backendNodeId": 200,
                                "nodeType": 1,
                                "nodeName": "INPUT",
                                "attributes": ["type", "text", "placeholder", "搜索"],
                            },
                            {
                                "nodeId": 30,
                                "backendNodeId": 300,
                                "nodeType": 1,
                                "nodeName": "INPUT",
                                "attributes": ["type", "file", "accept", "image/*"],
                            },
                        ],
                    }
                ],
            }
        ],
    }
}


class _FakeCDPLibrary:
    """模拟 cdp-use 的 CDPLibrary（client.send 指向它）。"""

    class DOM:
        @staticmethod
        async def getDocument(params=None, *, session_id=None):
            return _DOM_TREE

        @staticmethod
        async def describeNode(params=None, *, session_id=None):
            return {"node": {"backendNodeId": 0}}

    class DOMSnapshot:
        @staticmethod
        async def captureSnapshot(params=None, *, session_id=None):
            return _snapshot_response()

    class Accessibility:
        @staticmethod
        async def getFullAXTree(params=None, *, session_id=None):
            return {"nodes": []}

    class Runtime:
        @staticmethod
        async def evaluate(params=None, *, session_id=None):
            return {"result": {}}  # 无 objectId → JS 点击监听器检测返回空集

        @staticmethod
        async def getProperties(params=None, *, session_id=None):
            return {"result": []}

        @staticmethod
        async def releaseObject(params=None, *, session_id=None):
            return {}

    class Page:
        @staticmethod
        async def getLayoutMetrics(params=None, *, session_id=None):
            return {"visualViewport": {}, "cssVisualViewport": {}}

        @staticmethod
        async def getFrameTree(params=None, *, session_id=None):
            return {"frameTree": {"frame": {"id": "main"}}}

    class Target:
        @staticmethod
        async def getTargets(params=None, *, session_id=None):
            return {"targetInfos": []}

        @staticmethod
        async def attachToTarget(params=None, *, session_id=None):
            return {"sessionId": "fake"}

        @staticmethod
        async def detachFromTarget(params=None, *, session_id=None):
            return {}


class FakeClient:
    """符合 CDPLikeClient Protocol 的假客户端（send 是属性，非方法）。"""

    send = _FakeCDPLibrary()


async def main() -> None:
    client: CDPLikeClient = FakeClient()

    print("=" * 70)
    print("dom-snapshot 最小示例：build_dom_state(CDPLikeClient)")
    print("=" * 70)

    # ── 主入口：build_dom_state ──────────────────────────────────────
    #   async (client, session_id, prev_map, cfg) -> (SerializedDOMState, DOMCollectionMetrics)
    dom_state, metrics = await build_dom_state(client, session_id="demo")

    # ── 采集指标 ─────────────────────────────────────────────────────
    print("\n[采集指标 DOMCollectionMetrics]")
    print(f"  降级级别  = {metrics.degradation_level.value}")
    print(f"  总耗时    = {metrics.total_ms:.0f} ms")
    print(f"  各源状态  = {metrics.source_statuses}")

    # ── 给 LLM 看的文本树（核心产出）────────────────────────────────
    print("\n[element_tree_text] ← 这是给 LLM 看的页面结构文本树")
    print("-" * 70)
    print(dom_state.element_tree_text or "(空)")
    print("-" * 70)

    # ── selector_map：index → EnhancedDOMTreeNode ─────────────────
    print("\n[selector_map] ← index → EnhancedDOMTreeNode（模型用 [index] 定位元素）")
    for idx, node in sorted(dom_state.selector_map.items()):
        print(f"  [{idx}] <{node.tag_name}> attrs={node.attributes} xpath={node.xpath!r}")

    # ── file_inputs_meta：[File Inputs] 段数据 ──────────────────────
    print("\n[file_inputs_meta] ← [File Inputs] 段数据（消费方渲染）")
    for fi in dom_state.file_inputs_meta:
        print(f"  backend_node_id={fi.backend_node_id} accept={fi.accept!r} visible={fi.visible}")

    # ── page_stats：[Page Stats] 段数据 ─────────────────────────────
    print(f"\n[page_stats] ← [Page Stats] 段数据：{dom_state.page_stats}")


if __name__ == "__main__":
    asyncio.run(main())
