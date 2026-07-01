from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from services.nodes.reconcilers.nats_health import NatsHealthReconciler, _parse_uptime


def _rec():
    lock = MagicMock()
    lock.hold = MagicMock()
    r = NatsHealthReconciler(tick_lock=lock)
    fake_session = AsyncMock()
    fake_session.__aenter__.return_value = fake_session
    fake_session.__aexit__.return_value = False
    r._session_maker = MagicMock(return_value=fake_session)
    return r


def _varz(mem_mb=90, uptime_sec=9000, slow=0):
    resp = MagicMock()
    resp.json.return_value = {"mem": mem_mb * 1048576, "uptime_sec": uptime_sec, "slow_consumers": slow}
    return resp


def test_parse_uptime():
    assert _parse_uptime("2h30m15s") == 2 * 3600 + 30 * 60 + 15
    assert _parse_uptime("1d1h") == 86400 + 3600


async def test_healthy_no_alert():
    rec = _rec()
    with patch("httpx.AsyncClient") as Cli, patch(
        "services.nodes.reconcilers.nats_health.AlertService"
    ) as AS:
        Cli.return_value.__aenter__.return_value.get = AsyncMock(return_value=_varz())
        AS.return_value.record = AsyncMock()
        AS.return_value.resolve = AsyncMock()
        n = await rec.tick()
    assert n == 0
    AS.return_value.record.assert_not_awaited()


async def test_restart_detected():
    rec = _rec()
    rec._prev_uptime_sec = 10000  # previous uptime higher
    with patch("httpx.AsyncClient") as Cli, patch(
        "services.nodes.reconcilers.nats_health.AlertService"
    ) as AS:
        Cli.return_value.__aenter__.return_value.get = AsyncMock(return_value=_varz(uptime_sec=30))
        AS.return_value.record = AsyncMock()
        AS.return_value.resolve = AsyncMock()
        n = await rec.tick()
    assert n >= 1
    titles = [c.kwargs["title"] for c in AS.return_value.record.await_args_list]
    assert any("перезапустил" in t for t in titles)


async def test_high_memory_alert():
    rec = _rec()
    with patch("httpx.AsyncClient") as Cli, patch(
        "services.nodes.reconcilers.nats_health.AlertService"
    ) as AS:
        Cli.return_value.__aenter__.return_value.get = AsyncMock(return_value=_varz(mem_mb=800))
        AS.return_value.record = AsyncMock()
        AS.return_value.resolve = AsyncMock()
        n = await rec.tick()
    assert n >= 1
    titles = [c.kwargs["title"] for c in AS.return_value.record.await_args_list]
    assert any("память" in t for t in titles)
