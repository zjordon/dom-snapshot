# dom-snapshot 示例

> 演示怎么用 dom-snapshot 公共库：「CDP 客户端进 → DOM 文本出」。

按使用场景分四个示例，从易到难：

| 示例 | 是否需 Chrome | 适合谁看 | 演示重点 |
|---|---|---|---|
| [`hello_snapshot.py`](./hello_snapshot.py) | ❌ 开箱即跑 | 所有人（入门） | 核心契约 `build_dom_state`，直观看到文本树格式 |
| [`inspect_dom_state.py`](./inspect_dom_state.py) | ❌ 开箱即跑 | 写 agent / 采集层的人 | 消费 `SerializedDOMState` 的结构化数据（降级/定位/iframe） |
| [`dump_model_view.py`](./dump_model_view.py) | ✅ 需 Chrome + cdp-use | 只想拿模型输入的人 | 精简版：只采集并把 `element_tree_text` 写入文件，不打印其它内容 |
| [`snapshot_live_page.py`](./snapshot_live_page.py) | ✅ 需 Chrome + cdp-use | 真实网页调试 | 多功能版：采集 + 指标 + 诊断，控制台摘要 + 文件完整结果 |

## 快速开始

```bash
# 1. 最快上手（无需 Chrome）—— 看文本树长什么样
uv run python examples/hello_snapshot.py

# 2. 进阶（仍无需 Chrome）—— 看消费方怎么用结构化数据
uv run python examples/inspect_dom_state.py

# 3. 只拿模型输入（需 Chrome + cdp-use）—— element_tree_text 写入 _model_view.txt
chrome --remote-debugging-port=9222
uv run python examples/dump_model_view.py

# 4. 真实网页调试（需 Chrome + cdp-use）—— 采集 + 指标 + 诊断，写 _model_page_view.txt
uv run python examples/snapshot_live_page.py
```

## 核心用法一览

dom-snapshot 只有一个主入口：

```python
import asyncio
from dom_snapshot import build_dom_state, CDPLikeClient

async def main():
    client: CDPLikeClient = ...  # 任何符合 Protocol 的 CDP 客户端（如 cdp-use 的 CDPClient）
    dom_state, metrics = await build_dom_state(client, session_id="...")
    print(dom_state.element_tree_text)  # 给 LLM 看的文本树
    print(dom_state.selector_map)       # index → EnhancedDOMTreeNode

asyncio.run(main())
```

库**不自带 CDP 客户端**（零硬依赖）——调用方自己装 `cdp-use` 并传客户端进来，
或传任何实现了 `CDPLikeClient` Protocol 的对象（`hello_snapshot.py` 的 FakeClient 就是例子）。

## 设计约束

dom-snapshot 只负责「CDP 进 → DOM 文本出」。本目录的示例**不**演示：
- agent 动作执行（click/input）——那是 TreeWalker 的职责
- 段级 prompt 组装（`[Page DOM]` 标题拼接）——消费方的事
- 事件录制 / trace 产出——那是 treeforge 的职责

这些边界见仓库根 [`ARCHITECTURE.md`](../ARCHITECTURE.md)。
