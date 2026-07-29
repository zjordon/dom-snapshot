# dom-snapshot

> 给 LLM 看的网页 DOM 快照库：从浏览器（通过 CDP）采集页面结构，
> 经三源采集 + 五步过滤，产出 `[index]<tag attr=val /> text` 格式的文本树。
>
> 消费方：browser-use 类 agent（如 [TreeWalker](https://github.com/zjordon/TreeWalker)）的运行时，
> 以及 trace 蒸馏工具（如 [TreeForge](https://github.com/zjordon/treeforge)）的采集层。

## 这是什么

dom-snapshot 解决一个问题：**把一个网页的 DOM 转成 LLM 能读懂、能定位、能操作的文本**。

原始 DOM 有几万个节点、大量噪声（script/style/隐藏元素/广告）、语义稀薄。直接喂给 LLM 既超 token 又抓不住重点。
dom-snapshot 做三件事：

1. **三源采集**：并行拉取 DOM 树 / Snapshot（布局+可见性）/ Accessibility 树，交叉融合成增强节点
2. **五步过滤**：剪除噪声（script/style/SVG 子元素）、剔除被遮挡节点、传播型元素包围盒合并、给可交互元素编号
3. **文本格式化**：产出 `[index]<tag attr=val /> text` 格式的文本树，附 `[File Inputs]` / `[Page Stats]` 段

输出示例（节选）：

```
[142]<a id=nav_upload_btn />
    投稿
[3683]<input type=text placeholder=请输入稿件标题 maxlength=80 />
[3788]<div contenteditable=true />
[3819]<span />
    立即投稿
```

LLM 读这棵文本树就能：定位元素（用 `[index]`）、理解元素用途（靠 attr + 可见文本）、决定操作（click / input / upload_file）。

## 设计目标

- **单一实现，多端共享**：TreeWalker agent 运行时和 TreeForge 采集层用同一份快照代码，避免格式漂移
- **零业务耦合**：库不认识「agent 动作执行」「trace 蒸馏」「rerun-history」——只负责「CDP 客户端进 → DOM 文本出」
- **鸭子类型解耦**：只依赖 `CDPLikeClient` Protocol（`send(domain, method, params, session_id)`），不硬绑 `cdp-use` 包

## 来源

从 [TreeWalker](https://github.com/zjordon/TreeWalker) 的 `src/tree_walker/browser/` 抽取 5 个核心文件（约 3453 行）：

| 源文件 | 抽取后 |
|---|---|
| `views.py`（DOM 部分） | `dom_snapshot/models.py` |
| `cdp_timeout.py` | `dom_snapshot/cdp_timeout.py` |
| `paint_order.py` | `dom_snapshot/paint_order.py` |
| `dom.py` | `dom_snapshot/collector.py` |
| `serializer.py` | `dom_snapshot/serializer.py` |

抽取过程处理 3 个耦合点（循环依赖 / views 混合模型 / CDPClient 硬依赖），详见 [ARCHITECTURE.md](./ARCHITECTURE.md)。

## 快速使用

```python
import asyncio
from cdp_use import CDPClient
from dom_snapshot import build_dom_state

async def main():
    client = CDPClient(ws_url="ws://localhost:9222/...")
    await client.connect()
    # 传任何符合 CDPLikeClient 的对象 + session_id
    dom_state, metrics = await build_dom_state(client, session_id="...")
    print(dom_state.element_tree_text)   # 给 LLM 看的文本树
    print(dom_state.selector_map)        # index → EnhancedDOMTreeNode
    print(dom_state.file_inputs_meta)    # [File Inputs] 段数据

asyncio.run(main())
```

## 状态

🚧 **开发中**（P2.1 阶段）。抽取自 TreeWalker，尚未独立发版。
开发计划见 [ROADMAP.md](./ROADMAP.md)，架构设计见 [ARCHITECTURE.md](./ARCHITECTURE.md)，开发规范见 [AGENTS.md](./AGENTS.md)。

## 许可证

见 [LICENSE](./LICENSE)。
