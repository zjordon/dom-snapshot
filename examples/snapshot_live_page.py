"""连真 Chrome 示例：用 cdp-use 的 CDPClient 采集真实网页快照。

参照 TreeWalker 的 examples/debug_model_page_view.py 风格，但只演示 dom-snapshot
这条主线：「CDP 客户端进 → DOM 文本出」。本脚本不含 agent / prompt 组装，只产
element_tree_text + 结构化数据，是消费方（TreeWalker agent 运行时）拿到快照前的
那一步。

dom-snapshot 库本身不自带 CDP 客户端（零硬依赖）——调用方自己装 cdp-use 并传
客户端进来。这就是本例要演示的：怎么把一个 cdp-use CDPClient 喂给 build_dom_state。

前置条件：
  1. 安装 cdp-use（uv pip install cdp-use）。
     注意：cdp-use 是「本示例」的依赖，不是 dom-snapshot 库的依赖——库用
     CDPLikeClient Protocol 解耦、零硬依赖。本例要连真 Chrome 才需要它。
  2. Chrome 以调试端口启动：
       chrome --remote-debugging-port=9222
     并打开任意网页（默认采集当前活动标签页）。

用法：
    uv run python examples/snapshot_live_page.py [ws_url]
    # ws_url 省略时从 http://localhost:9222 自动发现
    # 例：uv run python examples/snapshot_live_page.py ws://localhost:9222/devtools/page/xxxx

输出：
    - 控制台打印摘要（element_tree_text 仅前 60 行，便于快速查看）
    - 完整结果（不截断：含完整 element_tree_text + 完整 selector_map 诊断）
      写入脚本同目录下的 _model_page_view.txt，便于编辑器搜索长文本。
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import urllib.request


def discover_ws_url(port: int = 9222) -> str | None:
    """从 Chrome 调试端口发现第一个页面标签的 ws_url。"""
    try:
        with urllib.request.urlopen(f"http://localhost:{port}/json", timeout=2) as resp:
            tabs = json.loads(resp.read())
    except Exception as e:
        print(f"无法连接 Chrome 调试端口 {port}：{e}", file=sys.stderr)
        return None
    for tab in tabs:
        if tab.get("type") == "page":
            return tab.get("webSocketDebuggerUrl")
    return None


async def main() -> None:
    # cdp-use 是「本示例」的依赖，不是 dom-snapshot 库的依赖。
    # 库本身用 CDPLikeClient Protocol 鸭子类型解耦，零硬依赖 cdp-use；
    # 但本例要连真 Chrome，需要一个真实 CDP 客户端，故用 cdp-use 的 CDPClient。
    try:
        from cdp_use import CDPClient
    except ImportError:
        print(
            "本示例需要 cdp-use（用于连真 Chrome）。\n"
            "注意：cdp-use 不是 dom-snapshot 库的依赖——库用 CDPLikeClient Protocol\n"
            "解耦，零硬依赖。本例为连真实浏览器才需要它。\n"
            "安装：uv pip install cdp-use（或 pip install cdp-use）",
            file=sys.stderr,
        )
        sys.exit(1)

    from dom_snapshot import build_dom_state

    ws_url = sys.argv[1] if len(sys.argv) > 1 else discover_ws_url()
    if not ws_url:
        print(
            "未找到 Chrome 调试端点。请以 --remote-debugging-port=9222 启动 Chrome，\n"
            "或显式传入 ws_url：uv run python examples/snapshot_live_page.py ws://...",
            file=sys.stderr,
        )
        sys.exit(1)

    print("=" * 80)
    print("dom-snapshot 连真 Chrome 示例")
    print("=" * 80)
    print(f"ws_url = {ws_url}")

    # emit() 同时打印到控制台并收集到 out（用于写文件，保证两者内容一致）
    out: list[str] = []

    def emit(text: str = "") -> None:
        print(text)
        out.append(text)

    emit()
    emit("=" * 80)
    emit("dom-snapshot 连真 Chrome 示例")
    emit("=" * 80)
    emit(f"ws_url = {ws_url}")

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_model_page_view.txt")

    # ── 1. 创建 cdp-use 客户端并握手 ──────────────────────────────────
    # CDPClient 天然符合 CDPLikeClient Protocol（client.send 是属性链式）
    client = CDPClient(ws_url)
    try:
        await client.start()
        emit("[1/4] CDP 握手完成")

        # ── 2. 找到当前页面 target，attach 拿 session_id ─────────────
        targets = await client.send.Target.getTargets({})
        session_id = None
        page_url = "?"
        for t in targets.get("targetInfos", []):
            if t.get("type") == "page":
                result = await client.send.Target.attachToTarget(
                    {"targetId": t["targetId"], "flatten": True},
                )
                session_id = result["sessionId"]
                page_url = t.get("url", "?")
                emit(f"[2/4] attach 到页面 target：{page_url[:60]}")
                break
        if not session_id:
            print("未找到 page 类型 target", file=sys.stderr)
            sys.exit(1)

        # ── 3. 采集快照（核心：dom-snapshot 的主入口）─────────────────
        #   build_dom_state(client, session_id, prev_map, cfg)
        #     -> (SerializedDOMState, DOMCollectionMetrics)
        dom_state, metrics = await build_dom_state(client, session_id=session_id)
        emit(
            f"[3/4] 采集完成：降级级别={metrics.degradation_level.value}，"
            f"耗时={metrics.total_ms:.0f}ms"
        )

        # ── 4. 输出产出 ────────────────────────────────────────────────
        tree_text = dom_state.element_tree_text
        emit(
            f"[4/4] element_tree_text：{len(tree_text)} 字符 / "
            f"{len(tree_text.splitlines())} 行 / selector_map {len(dom_state.selector_map)} 项"
        )

        # 采集指标
        emit()
        emit("=" * 80)
        emit("[采集指标] 各源状态（降级决策依据）")
        emit("=" * 80)
        for name, status in metrics.source_statuses.items():
            emit(f"  {name:12s} = {status}")

        # Page Stats
        emit()
        emit("=" * 80)
        emit("[Page Stats]")
        emit("=" * 80)
        for k, v in dom_state.page_stats.items():
            emit(f"  {k:12s} = {v}")

        # element_tree_text：控制台截断（前 60 行），文件写完整
        lines = tree_text.splitlines()
        emit()
        emit("=" * 80)
        emit(f"[element_tree_text] ← LLM 看到的页面结构（控制台显示前 60 行 / 共 {len(lines)} 行）")
        emit("=" * 80)
        for line in lines[:60]:
            print(line)  # 控制台：截断显示
        if len(lines) > 60:
            print(
                f"... (共 {len(lines)} 行，控制台已截断；完整内容见 {os.path.basename(out_path)})"
            )
        # 文件：完整 element_tree_text
        out.append("")  # 空行
        out.append("=" * 80)
        out.append(f"[element_tree_text 完整内容] 共 {len(lines)} 行")
        out.append("=" * 80)
        if tree_text:
            out.append(tree_text)

        # 诊断：selector_map（控制台前 10 项，文件全部）
        # 对照 debug_model_page_view.py 的发现：模型用 [index] 定位，index 应 = backend_node_id
        emit()
        emit("=" * 80)
        emit("[诊断] selector_map（控制台前 10 项 / 文件含全部，index 应 = backend_node_id）")
        emit("=" * 80)
        sorted_idxs = sorted(dom_state.selector_map.keys())
        for idx in sorted_idxs[:10]:
            node = dom_state.selector_map[idx]
            bid = node.backend_node_id
            warn = "" if idx == bid else f"   ⚠️ index({idx}) != backend_node_id({bid})"
            emit(f"  [{idx}] <{node.tag_name}> bid={bid}{warn}")
        # 文件：完整 selector_map 诊断
        out.append("")
        out.append(f"# selector_map 完整诊断（共 {len(sorted_idxs)} 项）")
        for idx in sorted_idxs:
            node = dom_state.selector_map[idx]
            bid = node.backend_node_id
            warn = "" if idx == bid else "   ⚠️ index != backend_node_id"
            out.append(f"  [{idx}] <{node.tag_name}> bid={bid} attrs={node.attributes}{warn}")

    finally:
        await client.stop()
        emit()
        emit("[完成] 客户端已关闭")

    # 写完整结果到文件（element_tree_text 等长文本不截断）
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print()
    print("=" * 80)
    print(f"完整结果已写入：{out_path}")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
