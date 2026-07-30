# dom-snapshot 路线图

> 本库的职责单一且边界清晰：从 TreeWalker 抽取 5 个 DOM 快照核心文件，处理 3 个耦合点，
> 成为 TreeWalker + treeforge 共用的独立公共库。
>
> 方案来源：[treeforge/docs/p2/README.md](https://github.com/zjordon/treeforge/blob/main/docs/p2/README.md) 第 3.1 节（P2.1 阶段）。

## 总体目标

把 TreeWalker 里「三源采集 + 五步过滤 → element_tree_text」这块代码（约 3453 行，5 个文件）
抽成独立 git 仓库，让 TreeWalker agent 运行时和 treeforge 采集层共享同一份快照实现。

**成功判据**：抽取后 TreeWalker 全量测试通过 + agent 端到端行为不变（产出 byte-for-byte 一致的 element_tree_text）。

---

## M1 —— 仓库初始化与脚手架

**目标**：搭好库的骨架，能 `pip install -e .` 本地开发。

- [x] git 仓库初始化（GitHub 创建，已有 .gitignore + LICENSE）
- [x] 文档骨架（README / ARCHITECTURE / ROADMAP）
- [x] `pyproject.toml`：包名 `dom-snapshot`、模块 `dom_snapshot`、Python ≥3.11、dev 依赖（pytest/ruff）
- [x] 目录骨架：`src/dom_snapshot/__init__.py`（空 public API）+ `tests/`
- [x] `.gitignore` 补充 `.zcode/`（对齐 treeforge 约定）
- [x] 首次提交 + 推送

**验收**：`uv sync --extra dev` 成功；`uv run python -c "import dom_snapshot"` 不报错（即使内容空）。

---

## M2 —— 核心抽取（5 文件迁移 + 3 耦合点处理）

**目标**：把 TreeWalker 的 5 个文件迁过来，处理 3 个耦合点，库内部能独立运行。

### M2.1 依赖核实（抽取前的关键一步）

- [x] 核实 `client.send` 的调用形式：是 `client.send.DOM.getDocument(...)`（属性链式）
      还是 `client.send("DOM", "getDocument", ...)`（参数式）？这决定 `CDPLikeClient` Protocol 的形状
      —— **结论：属性链式**，Protocol 建模为多级（send → _CDPLibrary → 六个 Domain 子 Protocol）
- [x] 核实 `DOMInteractedElement.load_from_enhanced_dom_tree` 对 `EnhancedDOMTreeNode` 的字段依赖
      （确认留在 TreeWalker 的聚合类型能正确读 dom-snapshot 的 DOM 模型）
      —— 9 个直接字段 + parent_node 链（xpath/hash/compute_stable_hash 间接读），全部保留进 models.py
- [x] 核实 TreeWalker `session.py:22-30` 对 dom.py 私有函数 `_attach_to_iframe_target` / `_build_frame_target_map` 的使用
      —— **结论：提为 public API**（去下划线），dom 内部采集也用，避免两仓库重复 CDP Target 薄封装

> M2.1 核实详细结论见 `docs/p2/m2-extraction-plan.md`。额外发现 ARCHITECTURE 3 处偏差并已修正：
> `DYNAMIC_CLASS_PATTERNS` 漏列（已补进 models.py）/ `MatchLevel` 漏列（留 TreeWalker）/ `DOMInteractedElement` 是 dataclass 非 pydantic。

### M2.2 逐文件迁移（按依赖顺序，从底向上）

- [x] `models.py`：从 TreeWalker `views.py` 拆出 DOM 核心 dataclass（见 ARCHITECTURE 第三节拆分清单）
      —— **剥离 pydantic**，纯 dataclass
- [x] `cdp_timeout.py`：迁移（`CDPSourceStatus(str, Enum)` → `StrEnum`，ruff UP042 现代化）
- [x] `_protocol.py`：新建 `CDPLikeClient` Protocol（完整多级：6 Domain 子 Protocol，基于 M2.1 核实结果）
- [x] `paint_order.py`：仅 import 路径调整（`views.SimplifiedNode` → `models.SimplifiedNode`）
- [x] `interactive.py`：从 TreeWalker `dom.py:74-218` 抽出 `ClickableElementDetector` + `is_interactive`
      （**破循环依赖**的关键）
- [x] `collector.py`：原 `dom.py`，调整 import（`views.*` → `models.*`，`cdp_use` → `_protocol`），
      iframe 函数去下划线提 public，`asyncio.TimeoutError` → `TimeoutError`（ruff UP041）
- [x] `serializer.py`：原 `serializer.py`，调整 import + 从 `interactive` 导入 `is_interactive`（不再懒导入 collector）

### M2.3 内部测试

- [x] 5 个测试文件（models/interactive/cdp_timeout/protocol/smoke_import）共 **90 项全过**
- [x] 端到端：FakeClient 跑通 `build_dom_state` 全流程（三源采集 + 五步过滤 + 序列化）
- [x] 抽取等价性验证：同输入下 dom-snapshot 产出 vs TreeWalker 原始产出一致
      —— ✅ **已验证**：bilibili 投稿页三个页面状态（upload/publish/upload-cover）各跑一次，
      dom-snapshot 与 TreeWalker 双方产出经 diff + MD5 三重核对 **byte-for-byte 完全一致**
      （见 `D:\temp\dom-snapshot-model-input\bili` vs `D:\temp\tree-walker-model-input\bili`）

**验收**：`uv run python -m pytest tests/` 通过（90 项）；`import dom_snapshot` 无循环依赖；独立跑 `build_dom_state` 能产出 `SerializedDOMState`。

---

## M3 —— TreeWalker 接入（跨工程改动）（当前）

**目标**：TreeWalker 改为依赖 dom-snapshot，删除本地 5 文件，agent 行为不变。

- [ ] dom-snapshot 发版 0.1.0（打 git tag，`pip install` 可用）
- [ ] TreeWalker `pyproject.toml` 加 `dom-snapshot>=0.1.0` 依赖
- [ ] TreeWalker 改 import：
      - `browser/session.py:22-30`：`from dom_snapshot import build_dom_state`
      - `agent/step.py` / `prompts/system_prompt.py` / `tools/actions.py` / `recorder/recorder.py`：
        `from tree_walker.browser.views import ...` → 从 `dom_snapshot` import DOM 类型 + 本地 import 聚合类型
      - `browser/views.py`：删 DOM 核心 dataclass（已迁走），保留聚合状态模型
      - `browser/__init__.py`：重导出调整
- [ ] 处理 M2.1 核实的 `_attach_to_iframe_target` / `_build_frame_target_map`（提为 public 或 session 端重实现）
- [ ] TreeWalker 全量测试
- [ ] TreeWalker agent 端到端验证（跑一个真实任务，确认快照行为不变）

**验收**：TreeWalker 所有测试通过；agent 跑 bilibili 投稿任务，DOM 快照与抽取前一致。
**回滚**：若出问题，revert import 改动 + 恢复本地 5 文件。

---

## M4 —— treeforge 接入（可选，P2.2 备用）

**目标**：treeforge 依赖 dom-snapshot（供采集层 `cdp_session.py` 使用）。

- [ ] treeforge `pyproject.toml` 加 `dom-snapshot>=0.1.0`
- [ ] `uv run python -c "from dom_snapshot import build_dom_state"` 不报错

**说明**：M4 可延后到 treeforge P2.2 真正开发采集层时再做。M1-M3 完成后 dom-snapshot 已可用。

---

## 里程碑速查

| 阶段 | 交付物 | 状态 | 备注 |
|---|---|---|---|
| **M1** | 仓库脚手架（pyproject + 目录 + 文档） | ✅ | 已完成（commit b4b4df0） |
| **M2** | 5 文件迁移 + 3 耦合点处理 + 内部测试 | ✅ | 已完成（90 项测试全过 + bilibili 真实页面等价性验证 byte-for-byte 一致） |
| **M3** | TreeWalker 接入（删本地 5 文件，全量测试） | 🔄 | 当前，跨工程，需端到端验证 |
| **M4** | treeforge 接入（可选） | ⏳ | P2.2 备用 |

---

## 风险与权衡

| 风险 | 影响 | 应对 |
|---|---|---|
| **`client.send` 调用形式核错** | CDPLikeClient Protocol 形状不对，运行时 AttributeError | M2.1 作为抽取第一步强制核实；先写个最小用例验证 cdp-use 客户端符合 Protocol |
| **views.py 拆分遗漏** | DOM 模型字段不全，collector/serializer 运行报错 | 按拆分清单逐项核对；用 TreeWalker 现有测试 fixture 验证 |
| **抽取引入回归** | TreeWalker agent 行为变化（快照格式漂移） | M3 强制端到端验证；保留回滚能力；抽取是纯重组不改逻辑 |
| **循环依赖没破干净** | import 报错或运行时 CircularImport | interactive.py 独立后，用 `python -c "import dom_snapshot"` 验证 import 链 |
| **跨工程依赖协调** | dom-snapshot 改动要同步 TreeWalker | M3 用 `pip install -e ../dom-snapshot` 本地开发；稳定后发版 |

---

## 不做（明确排除）

- **agent 动作执行**（click/input/navigate/upload_file）—— 那是 TreeWalker `session.py` 的职责，不属于快照库
- **段级 prompt 组装**（`[Page DOM]` / `[File Inputs]` 标题拼接）—— 消费方的事，库只产数据和主文本树
- **事件录制 / trace 产出** —— 那是 treeforge 采集层的职责
- **rerun-history 格式** —— TreeWalker 重放专属，与本库无关
- **DB / 持久化** —— 纯内存计算库，无状态
