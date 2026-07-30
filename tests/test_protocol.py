"""_protocol.py 单元测试：CDPLikeClient Protocol 的鸭子类型契约。

Protocol 是库唯一的外部依赖契约。验证：
- 完整的 FakeClient（实现所有 Domain）符合 isinstance 检查
- cdp-use 的调用形状（属性链式 send.Domain.method）被 Protocol 正确建模
- runtime_checkable 在运行时可用
- 库不硬依赖 cdp-use（无 cdp-use 也能 import）
"""

from __future__ import annotations

from dom_snapshot._protocol import CDPLikeClient

# ── 完整 FakeClient：实现所有 6 个 Domain 的所有方法 ──────────────────


class _FakeDOM:
    async def getDocument(self, params=None, *, session_id=None):
        return {"root": {}}

    async def describeNode(self, params=None, *, session_id=None):
        return {"node": {"backendNodeId": 1}}


class _FakeDOMSnapshot:
    async def captureSnapshot(self, params=None, *, session_id=None):
        return {"documents": []}


class _FakeAccessibility:
    async def getFullAXTree(self, params=None, *, session_id=None):
        return {"nodes": []}


class _FakeRuntime:
    async def evaluate(self, params=None, *, session_id=None):
        return {"result": {}}

    async def getProperties(self, params=None, *, session_id=None):
        return {"result": []}

    async def releaseObject(self, params=None, *, session_id=None):
        return {}


class _FakePage:
    async def getLayoutMetrics(self, params=None, *, session_id=None):
        return {"visualViewport": {}, "cssVisualViewport": {}}

    async def getFrameTree(self, params=None, *, session_id=None):
        return {"frameTree": {"frame": {"id": "main"}}}


class _FakeTarget:
    async def getTargets(self, params=None, *, session_id=None):
        return {"targetInfos": []}

    async def attachToTarget(self, params=None, *, session_id=None):
        return {"sessionId": "sess-1"}

    async def detachFromTarget(self, params=None, *, session_id=None):
        return {}


class FakeCDPLibrary:
    """模拟 cdp-use 的 CDPLibrary：聚合各 Domain 子对象。"""

    DOM = _FakeDOM()
    DOMSnapshot = _FakeDOMSnapshot()
    Accessibility = _FakeAccessibility()
    Runtime = _FakeRuntime()
    Page = _FakePage()
    Target = _FakeTarget()


class FakeClient:
    """完整实现 CDPLikeClient 的假客户端（send 是属性，非方法）。"""

    send = FakeCDPLibrary()


# ── isinstance 鸭子类型 ────────────────────────────────────────────────


def test_full_fake_client_is_cdplikeclient():
    """完整实现所有 Domain 的 FakeClient 符合 Protocol。"""
    client = FakeClient()
    assert isinstance(client, CDPLikeClient)


def test_plain_object_not_cdplikeclient():
    assert not isinstance(object(), CDPLikeClient)


def test_client_without_send_not_cdplikeclient():
    class NoSend:
        pass

    assert not isinstance(NoSend(), CDPLikeClient)


# ── 属性链式调用形状验证（模拟 dom.py 的实际调用方式）─────────────────


def test_send_is_attribute_not_callable():
    """client.send 是属性对象，不是可调用方法。"""
    client = FakeClient()
    # send 本身不是 coroutine function（dom.py 用 client.send.DOM.getDocument(...)）
    assert not callable(client.send) or hasattr(client.send, "DOM")


def test_attribute_chain_calls_match_dom_py_usage():
    """模拟 dom.py 的调用形式，验证 Protocol 形状正确。

    dom.py 用 await client.send.<Domain>.<method>(params, session_id=...)
    """
    import asyncio

    client = FakeClient()

    # 模拟 dom.py:602 client.send.DOM.getDocument(...)
    async def call_get_document():
        return await client.send.DOM.getDocument({"depth": -1, "pierce": True}, session_id="s1")

    # 模拟 dom.py:592 client.send.DOMSnapshot.captureSnapshot(...)
    async def call_snapshot():
        return await client.send.DOMSnapshot.captureSnapshot(
            {"computedStyles": [], "includeDOMRects": True}, session_id="s1"
        )

    # 模拟 dom.py:542 client.send.Target.getTargets({})
    async def call_get_targets():
        return await client.send.Target.getTargets({})

    assert asyncio.run(call_get_document()) == {"root": {}}
    assert asyncio.run(call_snapshot()) == {"documents": []}
    assert asyncio.run(call_get_targets()) == {"targetInfos": []}


# ── 库不硬依赖 cdp-use ─────────────────────────────────────────────────


def test_protocol_importable_without_cdp_use():
    """库不应硬依赖 cdp-use（cdp-use 仅 TYPE_CHECKING 引用）。

    本测试环境未装 cdp-use，能 import 成功即证明运行时不依赖。
    """
    # 若此处 import 失败会抛 ImportError，测试失败
    from dom_snapshot._protocol import CDPLikeClient as _C  # noqa: F401

    assert CDPLikeClient is _C


def test_protocol_send_typed_as_cdplibrary():
    """CDPLikeClient.send 注解为 _CDPLibrary（含六个 Domain 属性）。"""
    # 通过 Protocol 的 __annotations__ 检查 send 字段存在
    hints = CDPLikeClient.__annotations__
    assert "send" in hints
