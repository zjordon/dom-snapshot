"""cdp_timeout.py 单元测试：run_cdp_batch 两阶段超时 + 选择性重试。

用假 async factory 测试，不连真 CDP。覆盖：
- 全部成功（Phase 1 OK）
- 部分超时 → Phase 2 重试成功（RETRIED_OK）
- 部分失败（抛异常 → FAILED，不重试恢复除非 factory 再抛）
- 失败/超时后的 batch.get() 降级
- CDPSourceStatus / CDPBatchResult 行为
"""

from __future__ import annotations

import asyncio

from dom_snapshot.cdp_timeout import (
    CDPBatchResult,
    CDPSourceResult,
    CDPSourceStatus,
    run_cdp_batch,
)

# ── CDPSourceStatus（StrEnum 行为）─────────────────────────────────────


def test_cdp_source_status_str_enum_values():
    assert CDPSourceStatus.OK == "ok"
    assert CDPSourceStatus.TIMEOUT == "timeout"
    assert CDPSourceStatus.FAILED == "failed"
    assert CDPSourceStatus.RETRIED_OK == "retried_ok"
    # .value 是 str（collector metrics.source_statuses 依赖）
    assert CDPSourceStatus.OK.value == "ok"


# ── CDPBatchResult / CDPSourceResult ──────────────────────────────────


def test_batch_result_get_returns_value_for_ok():
    batch = CDPBatchResult()
    batch.sources["dom"] = CDPSourceResult(name="dom", status=CDPSourceStatus.OK, value={"root": 1})
    assert batch.get("dom") == {"root": 1}


def test_batch_result_get_returns_default_for_failed():
    batch = CDPBatchResult()
    batch.sources["dom"] = CDPSourceResult(name="dom", status=CDPSourceStatus.FAILED)
    assert batch.get("dom", "fallback") == "fallback"


def test_batch_result_get_returns_value_for_retried_ok():
    batch = CDPBatchResult()
    batch.sources["dom"] = CDPSourceResult(
        name="dom", status=CDPSourceStatus.RETRIED_OK, value={"ok": True}
    )
    assert batch.get("dom") == {"ok": True}


def test_batch_result_failed_names():
    batch = CDPBatchResult()
    batch.sources["ok_src"] = CDPSourceResult(name="ok_src", status=CDPSourceStatus.OK)
    batch.sources["fail_src"] = CDPSourceResult(name="fail_src", status=CDPSourceStatus.FAILED)
    batch.sources["timeout_src"] = CDPSourceResult(
        name="timeout_src", status=CDPSourceStatus.TIMEOUT
    )
    assert set(batch.failed_names) == {"fail_src", "timeout_src"}


# ── run_cdp_batch 场景 ─────────────────────────────────────────────────


def test_run_cdp_batch_all_success():
    """Phase 1 全部 OK，无重试。"""

    async def ok_factory():
        await asyncio.sleep(0)
        return {"data": 1}

    result = asyncio.run(run_cdp_batch({"src": ok_factory}, first_timeout=2.0, retry_timeout=1.0))
    assert result.sources["src"].status == CDPSourceStatus.OK
    assert result.sources["src"].value == {"data": 1}
    assert result.failed_names == []


def test_run_cdp_batch_timeout_then_retry_ok():
    """Phase 1 超时 → Phase 2 重试成功（RETRIED_OK）。

    用一个有状态的 factory：第一次慢（超 first_timeout），第二次快。
    """

    call_count = {"n": 0}

    async def flaky_factory():
        call_count["n"] += 1
        if call_count["n"] == 1:
            await asyncio.sleep(5.0)  # 远超 first_timeout，必然 Phase 1 超时
        return {"recovered": True}

    result = asyncio.run(
        run_cdp_batch({"src": flaky_factory}, first_timeout=0.1, retry_timeout=2.0)
    )
    # 第一次超时，第二次（重试）成功
    assert result.sources["src"].status == CDPSourceStatus.RETRIED_OK
    assert result.sources["src"].value == {"recovered": True}


def test_run_cdp_batch_failure_not_recovered():
    """factory 持续抛异常 → FAILED（重试也失败仍是 FAILED）。"""

    async def failing_factory():
        raise RuntimeError("CDP error")

    result = asyncio.run(
        run_cdp_batch({"src": failing_factory}, first_timeout=2.0, retry_timeout=1.0)
    )
    assert result.sources["src"].status == CDPSourceStatus.FAILED
    assert "CDP error" in (result.sources["src"].error or "")


def test_run_cdp_batch_mixed_sources():
    """混合：一个 OK，一个 FAILED，一个超时后重试 OK。"""

    flaky_state = {"first": True}

    async def ok_src():
        return {"ok": 1}

    async def fail_src():
        raise ValueError("boom")

    async def flaky_src():
        if flaky_state["first"]:
            flaky_state["first"] = False
            await asyncio.sleep(5.0)
        return {"flaky": 1}

    result = asyncio.run(
        run_cdp_batch(
            {"ok": ok_src, "fail": fail_src, "flaky": flaky_src},
            first_timeout=0.1,
            retry_timeout=2.0,
        )
    )
    assert result.sources["ok"].status == CDPSourceStatus.OK
    assert result.sources["fail"].status == CDPSourceStatus.FAILED
    assert result.sources["flaky"].status == CDPSourceStatus.RETRIED_OK
    assert set(result.failed_names) == {"fail"}


def test_run_cdp_batch_get_degradation_fallback():
    """模拟 collector 的降级逻辑：batch.get 对失败源返回 default。"""
    batch = CDPBatchResult()
    batch.sources["snapshot"] = CDPSourceResult(
        name="snapshot", status=CDPSourceStatus.OK, value={"d": 1}
    )
    batch.sources["dom_tree"] = CDPSourceResult(name="dom_tree", status=CDPSourceStatus.FAILED)

    # collector: snapshot = batch.get('snapshot'); dom_tree = batch.get('dom_tree')
    snapshot = batch.get("snapshot")
    dom_tree = batch.get("dom_tree")
    assert snapshot == {"d": 1}
    assert dom_tree is None  # 失败源 → None（collector 据此判定 FAILED 降级）


def test_run_cdp_batch_total_ms_positive():
    """total_ms 应为正数（耗时统计）。"""

    async def quick():
        await asyncio.sleep(0.01)
        return 1

    result = asyncio.run(run_cdp_batch({"s": quick}, first_timeout=2.0))
    assert result.total_ms > 0
