# 项目规范

> 本文件是 dom-snapshot 公共库的开发规范，agent 在本工作区作业时必须遵守。
> 通用部分参照姊妹项目 treeforge/AGENTS.md，按公共库特点（无 CLI、无 LLM、无外部服务）裁剪。

## 代码风格

- **缩进使用 4 个空格**，不使用 tab。编辑文件时务必保持一致，否则 Edit 工具会因为字符不匹配而失败。
- **行宽 100**（见 `pyproject.toml` `[tool.ruff] line-length = 100`）。E501（超长行）在 ruff 里已 ignore，但新代码仍应尽量控制在 100 列内。
- **格式化 / lint 统一走 ruff**：`uv run ruff format .` 格式化，`uv run ruff check .` 检查。ruff 配置见 `pyproject.toml`：
  - lint 规则集：`E, F, W, I, UP, B`（isort 已启用，first-party 包为 `dom_snapshot`）。
  - target：`py311`。
- **类型注解**：公共函数（public API）必须带类型注解，模块顶部统一加 `from __future__ import annotations`。
- **docstring**：模块级三引号 docstring 用中文，描述该模块职责。

## 运行环境

- **开发环境是 Windows**，命令行工具主要用 Git Bash（MSYS2）。本仓库测试用的 Bash 命令在 Git Bash 下可跑。
- **优先使用专用工具**而非 shell：读文件用 Read，搜索用 Grep/Glob，改文件用 Edit。需要 `find/grep/cat` 时注意 Git Bash 的 GNU 实现与 PowerShell 行为不同。
- 路径分隔符：仓库内引用统一用正斜杠 `/`（跨平台），绝对路径按平台写。

## 包管理

- **使用 uv 管理 Python 包**，不要使用 pip。同步依赖用 `uv sync --extra dev`。
- **运行 Python 必须用 `uv run`**，例如 `uv run python -m pytest ...`、`uv run ruff check .`。直接调用系统 `python` 会因为找不到虚拟环境里的 `dom_snapshot` 而失败。
- **新增依赖**：编辑 `pyproject.toml` 的 `[project] dependencies`（运行时）或 `[project.optional-dependencies] dev`（开发期），再 `uv sync`。不要手动 `pip install` 后忘了登记。
- **最小依赖原则**：本库是公共库，尽量少依赖外部包。当前仅需 stdlib；对 `cdp-use` 用 `CDPLikeClient` Protocol 解耦（仅 `TYPE_CHECKING` 引用），不硬依赖。不引入任何 LLM SDK、Web 框架、DB 驱动。

## 单元测试要求

- **任何代码改动后都必须运行相关单元测试**，确保已有测试全部通过后再结束。
- **新增功能或修改功能时必须同步增加测试用例**，覆盖正常路径和关键边界情况。
- **测试不连真浏览器**：用录制的 CDP 响应 fixture（JSON），不依赖 Chrome 运行时，不发真实 CDP 命令。
- **抽取等价性是核心判据**：从 TreeWalker 抽取的代码，同输入下 dom-snapshot 产出必须与 TreeWalker 原始产出一致（防回归）。
- 测试运行命令：
  - 全量：`uv run python -m pytest tests/ -x -v`
  - 单文件：`uv run python -m pytest tests/test_xxx.py -v`
- pytest 配置见 `pyproject.toml`：`testpaths=["tests"]`、`pythonpath=["src"]`、`addopts="-ra -q"`。
- 共享 fixture 放 `tests/conftest.py`，CDP 响应样本放 `tests/fixtures/`。

## 目录约定

- `src/dom_snapshot/` —— 库源码（5 个从 TreeWalker 迁移的文件 + 新增的 `interactive.py` / `_protocol.py`）。详见 `ARCHITECTURE.md` 模块分层。
- `tests/` —— 单元测试（fixture 用录制的 CDP 响应 JSON，不连真浏览器）。
- `ARCHITECTURE.md` —— 架构设计（三源采集 / 五步过滤 / 耦合点 / public API），改库内部逻辑时必读。
- `ROADMAP.md` —— 开发路线（M1-M4 阶段）。

**库的职责边界**（改代码时务必守住）：dom-snapshot 只负责「CDP 客户端进 → DOM 文本出」。
不做 agent 动作执行、不做段级 prompt 组装、不做事件录制 / trace 产出、不做 rerun-history、无状态无持久化。
这些是消费方（TreeWalker / treeforge）的职责，不要在本库里实现。

## Git 提交规则

- **修改完代码后不要主动 `git commit`**，也不要主动 `git push`。
- **不要在任务结束时主动询问"要不要提交"**——这相当于变相催促用户提交。完成代码改动并跑完测试后直接结束汇报即可。
- 即使测试全过、ruff 无告警、改动看起来完整且符合 plan，也**不主动提交**。
- 只有当用户**明确要求提交**（如"提交一下"、"commit"、"创建 PR"）时，才执行 git 提交流程。
- 用户授权提交时，仍需遵守通用 git 安全约定：不 force push、不 amend 已发布提交、不跳过 hooks、不提交 `.env` / `.venv` / `.zcode/`（均已在 `.gitignore`）。
- 当前默认分支是 `main`；如需开新功能分支再操作，不要直接在 `main` 上做大改动除非用户要求。
