"""CDPLikeClient Protocol：dom-snapshot 唯一的外部依赖契约。

库本身不硬依赖任何 CDP 客户端包（如 cdp-use），只要求调用方传入一个符合
本 Protocol 的对象。cdp-use 的 ``CDPClient`` 天然符合（见下方调用形式），
任何实现了相同接口的对象（含测试用的假客户端）都可传入 build_dom_state。

调用形式（属性链式，与 cdp-use 一致）::

    await client.send.<Domain>.<method>(params_dict, session_id=...)

其中 ``client.send`` 是属性对象（非可调用），返回一个含各 Domain 子对象
的库对象；每个 Domain 子对象的 ``method`` 都是 ``async``，签名统一为
``(params: dict | None, *, session_id: str | None) -> dict``，返回的
coroutine await 后得到 CDP 响应字典。

本 Protocol 按需建模 collector.py 实际触达的 6 个 Domain：
DOM / DOMSnapshot / Accessibility / Runtime / Page / Target。
新增 CDP 调用时，在对应 Domain Protocol 里补方法签名即可。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    # 仅类型检查用，运行时不导入，库不硬依赖 cdp-use。
    from cdp_use import CDPClient  # noqa: F401


@runtime_checkable
class _DOMDomain(Protocol):
    """CDP ``DOM`` Domain（collector 用于取文档树、描述节点）。"""

    async def getDocument(
        self,
        params: dict | None = None,
        *,
        session_id: str | None = None,
    ) -> dict:
        """``DOM.getDocument``：返回 root DOM 节点（含子树）。"""
        ...

    async def describeNode(
        self,
        params: dict | None = None,
        *,
        session_id: str | None = None,
    ) -> dict:
        """``DOM.describeNode``：按 objectId 描述节点（取 backendNodeId）。"""
        ...


@runtime_checkable
class _DOMSnapshotDomain(Protocol):
    """CDP ``DOMSnapshot`` Domain（布局/可见性/坐标/paintOrder 数据源）。"""

    async def captureSnapshot(
        self,
        params: dict | None = None,
        *,
        session_id: str | None = None,
    ) -> dict:
        """``DOMSnapshot.captureSnapshot``：捕获布局快照（含 computedStyles/bounds/paintOrder）。"""
        ...


@runtime_checkable
class _AccessibilityDomain(Protocol):
    """CDP ``Accessibility`` Domain（语义角色/名称/状态数据源）。"""

    async def getFullAXTree(
        self,
        params: dict | None = None,
        *,
        session_id: str | None = None,
    ) -> dict:
        """``Accessibility.getFullAXTree``：返回无障碍树节点列表。"""
        ...


@runtime_checkable
class _RuntimeDomain(Protocol):
    """CDP ``Runtime`` Domain（JS 执行、对象属性、对象释放）。"""

    async def evaluate(
        self,
        params: dict | None = None,
        *,
        session_id: str | None = None,
    ) -> dict:
        """``Runtime.evaluate``：执行 JS 表达式（JS 点击监听器检测用）。"""
        ...

    async def getProperties(
        self,
        params: dict | None = None,
        *,
        session_id: str | None = None,
    ) -> dict:
        """``Runtime.getProperties``：取对象属性（解析 JS 返回的数组元素）。"""
        ...

    async def releaseObject(
        self,
        params: dict | None = None,
        *,
        session_id: str | None = None,
    ) -> dict:
        """``Runtime.releaseObject``：释放 RemoteObject 引用。"""
        ...


@runtime_checkable
class _PageDomain(Protocol):
    """CDP ``Page`` Domain（设备像素比、frame 树）。"""

    async def getLayoutMetrics(
        self,
        params: dict | None = None,
        *,
        session_id: str | None = None,
    ) -> dict:
        """``Page.getLayoutMetrics``：取布局度量（visualViewport，用于算设备像素比）。"""
        ...

    async def getFrameTree(
        self,
        params: dict | None = None,
        *,
        session_id: str | None = None,
    ) -> dict:
        """``Page.getFrameTree``：取 frame 层级树（AX 树按 frame 并行采集用）。"""
        ...


@runtime_checkable
class _TargetDomain(Protocol):
    """CDP ``Target`` Domain（跨源 iframe target 生命周期）。"""

    async def getTargets(
        self,
        params: dict | None = None,
        *,
        session_id: str | None = None,
    ) -> dict:
        """``Target.getTargets``：列所有 target（构建 frameId→targetId 映射）。"""
        ...

    async def attachToTarget(
        self,
        params: dict | None = None,
        *,
        session_id: str | None = None,
    ) -> dict:
        """``Target.attachToTarget``：附加到 target，返回独立 sessionId。"""
        ...

    async def detachFromTarget(
        self,
        params: dict | None = None,
        *,
        session_id: str | None = None,
    ) -> dict:
        """``Target.detachFromTarget``：从 target 分离（iframe 采集后清理）。"""
        ...


@runtime_checkable
class _CDPLibrary(Protocol):
    """``client.send`` 的形状：聚合各 CDP Domain 子对象的库对象。"""

    DOM: _DOMDomain
    DOMSnapshot: _DOMSnapshotDomain
    Accessibility: _AccessibilityDomain
    Runtime: _RuntimeDomain
    Page: _PageDomain
    Target: _TargetDomain


@runtime_checkable
class CDPLikeClient(Protocol):
    """快照库唯一的外部依赖契约：一个能发 CDP 命令的客户端。

    cdp-use 的 ``CDPClient`` 天然符合——其 ``send`` 属性是 ``CDPLibrary``，
    暴露 DOM/DOMSnapshot/Accessibility/Runtime/Page/Target 六个 Domain 子对象，
    每个方法都是 ``async (params: dict | None, *, session_id: str | None) -> dict``。

    任何实现此 Protocol 的对象都可传入 ``build_dom_state``（含测试用假客户端）。
    ``runtime_checkable`` 使 ``isinstance(client, CDPLikeClient)`` 在运行时可用。
    """

    send: _CDPLibrary


# 便于类型注解与文档引用的别名（build_dom_state 的 client 参数类型）
CDPLikeClientT = Any  # 运行时保持宽松；类型层用 CDPLikeClient Protocol
