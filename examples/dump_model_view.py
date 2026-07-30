"""精简示例：只采集页面并把「发给模型看的文本树」写入文件，不打印其它内容。

对比 snapshot_live_page.py（带采集指标 / Page Stats / 诊断的多功能版），本脚本
只做一件事：连真 Chrome → build_dom_state → 把 element_tree_text 原样写入文件。

element_tree_text 就是 dom-snapshot 产出的「给 LLM 看的页面结构」（ARCHITECTURE 第五节），
即消费方拼进 [Page DOM] 段的那个文本树主体。本脚本输出的是纯文本树，不含段级标题
（[Page DOM] / [File Inputs] 等标题由消费方 TreeWalker 在 build_state_message 里拼，
不属于本库职责）。

前置条件：
  1. 安装 cdp-use（uv pip install cdp-use）。同 snapshot_live_page.py：cdp-use 是
     「本示例」的依赖，不是 dom-snapshot 库的依赖（库用 CDPLikeClient Protocol 解耦）。
  2. Chrome 以调试端口启动：chrome --remote-debugging-port=9222，并打开目标网页。

用法：
    uv run python examples/dump_model_view.py [ws_url] [out_path]
    # ws_url 省略时从 http://localhost:9222 自动发现
    # out_path 省略时写入脚本同目录下的 _model_view.txt
"""

from __future__ import annotations

import asyncio
import os
import sys

# 复用 snapshot_live_page 的 ws_url 发现逻辑（同目录导入）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from snapshot_live_page import discover_ws_url  # noqa: E402


async def main() -> None:
    # cdp-use 是本示例的依赖（连真 Chrome 用），不是 dom-snapshot 库的依赖。
    try:
        from cdp_use import CDPClient
    except ImportError:
        sys.exit(
            "本示例需要 cdp-use（用于连真 Chrome，非 dom-snapshot 库依赖）。\n"
            "安装：uv pip install cdp-use"
        )

    from dom_snapshot import build_dom_state

    ws_url = sys.argv[1] if len(sys.argv) > 1 else discover_ws_url()
    if not ws_url:
        sys.exit(
            "未找到 Chrome 调试端点。请以 --remote-debugging-port=9222 启动 Chrome，\n"
            "或显式传入 ws_url：uv run python examples/dump_model_view.py ws://..."
        )

    default_out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_model_view.txt")
    out_path = sys.argv[2] if len(sys.argv) > 2 else default_out

    # 连接 → attach 当前页面 → 采集（流程同 snapshot_live_page.py，但不打印过程信息）
    client = CDPClient(ws_url)
    try:
        await client.start()

        targets = await client.send.Target.getTargets({})
        session_id = None
        for t in targets.get("targetInfos", []):
            if t.get("type") == "page":
                result = await client.send.Target.attachToTarget(
                    {"targetId": t["targetId"], "flatten": True},
                )
                session_id = result["sessionId"]
                break
        if not session_id:
            sys.exit("未找到 page 类型 target")

        # dom-snapshot 主入口：CDP 进 → DOM 文本出
        dom_state, _metrics = await build_dom_state(client, session_id=session_id)
    finally:
        await client.stop()

    # 唯一输出：把发给模型看的文本树写入文件（纯 element_tree_text，不含其它内容）
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(dom_state.element_tree_text)
    print(f"已写入：{out_path}（{len(dom_state.element_tree_text)} 字符）")


if __name__ == "__main__":
    asyncio.run(main())
