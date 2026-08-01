# dom-snapshot

> 给 LLM 看的网页 DOM 快照库:从浏览器(通过 CDP)采集页面结构,
> 经三源采集 + 五步过滤,产出 `[index]<tag attr=val /> text` 格式的文本树。
>
> 消费方:browser-use 类 agent(如 [TreeWalker](https://github.com/zjordon/TreeWalker))的运行时,
> 以及 trace 蒸馏工具(如 [TreeForge](https://github.com/zjordon/treeforge))的采集层。

[![version](https://img.shields.io/badge/version-0.1.0-blue)]()
[![python](https://img.shields.io/badge/python-%E2%89%A53.11-blue)]()
[![license](https://img.shields.io/badge/license-CC%20BY--NC%204.0-green)]()

**状态**:✅ v0.1.0 已发版。TreeWalker(agent 运行时)与 treeforge(采集层)均已接入,
三个工程共享同一份快照实现。

---

## 这是什么

dom-snapshot 解决一个问题:**把一个网页的 DOM 转成 LLM 能读懂、能定位、能操作的文本**。

原始 DOM 有几万个节点、大量噪声(script/style/隐藏元素/广告)、语义稀薄。直接喂给 LLM 既超 token 又抓不住重点。
dom-snapshot 做三件事:

1. **三源采集**:并行拉取 DOM 树 / Snapshot(布局+可见性)/ Accessibility 树,交叉融合成增强节点
2. **五步过滤**:剪除噪声(script/style/SVG 子元素)、剔除被遮挡节点、传播型元素包围盒合并、给可交互元素编号
3. **文本格式化**:产出 `[index]<tag attr=val /> text` 格式的文本树,附 `[File Inputs]` / `[Page Stats]` 段

输出示例(节选):

```
[142]<a id=nav_upload_btn />
    投稿
[3683]<input type=text placeholder=请输入稿件标题 maxlength=80 />
[3788]<div contenteditable=true />
[3819]<span />
    立即投稿
```

LLM 读这棵文本树就能:定位元素(用 `[index]`)、理解元素用途(靠 attr + 可见文本)、决定操作(click / input / upload_file)。

## 设计目标

- **单一实现,多端共享**:TreeWalker agent 运行时和 TreeForge 采集层用同一份快照代码,避免格式漂移
- **零业务耦合**:库不认识「agent 动作执行」「trace 蒸馏」「rerun-history」——只负责「CDP 客户端进 → DOM 文本出」
- **零运行时依赖**:`dependencies = []`。CDP 客户端通过 `CDPLikeClient` Protocol(鸭子类型)解耦,
  不硬绑 `cdp-use` 包——调用方自己装 cdp-use 传客户端进来,或传任何兼容实现

## 安装

v0.1.0 尚未发布到 PyPI,目前从 git tag 安装:

```bash
pip install "dom-snapshot @ git+https://github.com/zjordon/dom-snapshot.git@v0.1.0"
# 或 uv
uv pip install "dom-snapshot @ git+https://github.com/zjordon/dom-snapshot.git@v0.1.0"
```

> 库本身零运行时依赖。若要连真实 Chrome,需另装 `cdp-use`(见 [examples](./examples/))。

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

更多示例见 [`examples/`](./examples/)(含开箱即跑的 FakeClient 版,无需 Chrome):

| 示例 | 需 Chrome | 演示重点 |
|---|---|---|
| [`hello_snapshot.py`](./examples/hello_snapshot.py) | ❌ | 核心契约 `build_dom_state`,直观看到文本树格式 |
| [`inspect_dom_state.py`](./examples/inspect_dom_state.py) | ❌ | 消费结构化数据(降级/定位/iframe) |
| [`dump_model_view.py`](./examples/dump_model_view.py) | ✅ | 精简版:只把 `element_tree_text` 写入文件 |
| [`snapshot_live_page.py`](./examples/snapshot_live_page.py) | ✅ | 多功能版:采集 + 指标 + 诊断 |

## Public API

只暴露一个主入口 + 数据模型 + Protocol(共 23 项):

| 类别 | 主要导出 |
|---|---|
| **主入口** | `build_dom_state` / `EMPTY_DOM_STATE` |
| **iframe target 工具** | `build_frame_target_map` / `attach_to_iframe_target` |
| **数据模型** | `SerializedDOMState` / `EnhancedDOMTreeNode` / `SimplifiedNode` / `FileInputInfo` / `DOMRect` / `DOMCollectionConfig` / `DOMCollectionMetrics` / `DOMDegradationLevel` / `NodeType` … |
| **常量/函数** | `DEFAULT_INCLUDE_ATTRIBUTES` / `STATIC_ATTRIBUTES` / `DYNAMIC_CLASS_PATTERNS` / `filter_dynamic_classes` |
| **协议** | `CDPLikeClient`(CDP 客户端鸭子类型) |

```python
from dom_snapshot import CDPLikeClient  # 鸭子类型契约,cdp-use 的 CDPClient 天然符合
```

## 项目结构

```
src/dom_snapshot/
├── __init__.py       # public API(23 项)
├── _protocol.py      # CDPLikeClient Protocol(解耦 cdp-use,零硬依赖)
├── models.py         # DOM 数据模型(纯 dataclass,从 views.py 拆出)
├── cdp_timeout.py    # 两阶段超时批处理
├── paint_order.py    # Step 2 遮挡算法
├── interactive.py    # ClickableElementDetector + is_interactive(破循环依赖)
├── collector.py      # 三源采集 + 增强树构建(原 dom.py)
└── serializer.py     # 五步过滤 + 文本格式化(原 serializer.py)

examples/             # 4 个示例(2 个开箱即跑 + 2 个连真 Chrome)
tests/                # 90 项单元测试(不连真浏览器)
```

## 来源

从 [TreeWalker](https://github.com/zjordon/TreeWalker) 的 `src/tree_walker/browser/` 抽取 5 个核心文件(约 3453 行):

| 源文件 | 抽取后 |
|---|---|
| `views.py`(DOM 部分) | `dom_snapshot/models.py` |
| `cdp_timeout.py` | `dom_snapshot/cdp_timeout.py` |
| `paint_order.py` | `dom_snapshot/paint_order.py` |
| `dom.py` | `dom_snapshot/collector.py` + `interactive.py` |
| `serializer.py` | `dom_snapshot/serializer.py` |

抽取处理了 3 个耦合点(循环依赖 / views 混合模型 / CDPClient 硬依赖),
并经 **bilibili 投稿页真实页面验证**:dom-snapshot 产出与 TreeWalker 原始产出 **byte-for-byte 一致**(无损抽取)。

## 文档

- [ARCHITECTURE.md](./ARCHITECTURE.md) —— 架构设计(三源采集 / 五步过滤 / 耦合点处理 / public API)
- [ROADMAP.md](./ROADMAP.md) —— 开发路线(M1-M4 全部完成)
- [AGENTS.md](./AGENTS.md) —— 开发规范
- [docs/p2/m2-extraction-plan.md](./docs/p2/m2-extraction-plan.md) —— M2 抽取实施计划存档

## 许可证

[CC BY-NC 4.0](./LICENSE)(署名-非商业性使用 4.0 国际)
