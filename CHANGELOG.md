# Changelog

本库所有显著变更记录于此。格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [SemVer](https://semver.org/lang/zh-CN/)。

## [0.1.1] - 2026-09-13

### Fixed

- 单字符文本节点不再被序列化误杀（#1）：TEXT_NODE 保留条件 `len(text.strip()) > 1` 把
  个位数数值（0-9，如报表 qty 列 `4/3/3/2/2`）静默丢弃，只留 `<td />` 空壳。改为共享谓词
  `_is_meaningful_text`（`len(text) > 1 or text.isalnum()`，建树与渲染两处共用）：
  个位数/单字母/CJK 单字保留；装饰符（`•`/`|`/`·`）仍滤——继承 browser-use 噪声
  过滤意图不破。新增 `tests/test_text_filter.py` 12 项，全量 102 项通过，零回归。

### Changed

- 协议由 MIT 改为 CC BY-NC 4.0（对齐 TreeWalker）。

### Docs

- ROADMAP 同步 M3/M4 完成（四里程碑全部 ✅）；README 补全已完成状态（发版/安装/Public API/项目结构）。
- 归档 issue #1 原文（`docs/issue/`）、修复实施方案（`docs/bug-fix/`）、
  code review 结果（`docs/code-review/`，初审 3 findings 处置后复审 0 findings）。

## [0.1.0] - 2026-07-30

首个版本：从 TreeWalker 抽取 5 文件（3453 行）为独立公共库。

- 三源采集（DOM 树 / Snapshot / Accessibility）+ 五步过滤，产出
  `[index]<tag attr=val /> text` 格式文本树（`element_tree_text`）及
  selector_map / file_inputs_meta / page_stats 结构化数据。
- `CDPLikeClient` Protocol 鸭子类型解耦（属性链式 `send.<Domain>.<method>`），
  库零运行时依赖、零硬依赖 cdp-use。
- 处理 3 个耦合点：dom ↔ serializer 循环依赖（interactive.py 独立）、
  views.py 混合模型（DOM 核心剥离 pydantic）、cdp_use 硬依赖（Protocol 解耦）。
- 90 项单元测试；bilibili 真实页面抽取等价性验证 byte-for-byte 一致。
- TreeWalker（agent 运行时）与 treeforge（采集层）双端接入，三工程共享同一份快照实现。
