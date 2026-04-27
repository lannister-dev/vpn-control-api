from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from shared.reconciler.watchdog import ReconcilerWatchdog
from shared.reconciler.watchdog import watchdog as default_watchdog


def add_healthz(app: FastAPI) -> None:
    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict:
        return {"status": "ok"}


def add_reconciler_healthz(
    app: FastAPI,
    *,
    watchdog: ReconcilerWatchdog = default_watchdog,
) -> None:
    @app.get("/healthz/reconcilers", include_in_schema=False)
    async def healthz_reconcilers() -> JSONResponse:
        statuses = watchdog.statuses()
        alive = all(s.alive for s in statuses)
        body = {
            "alive": alive,
            "reconcilers": [
                {
                    "name": s.name,
                    "silence_sec": round(s.silence_sec, 1),
                    "max_silence_sec": round(s.max_silence_sec, 1),
                    "alive": s.alive,
                }
                for s in statuses
            ],
        }
        return JSONResponse(status_code=200 if alive else 503, content=body)

    @app.get("/healthz/live", include_in_schema=False, response_model=None)
    async def healthz_live():
        if watchdog.is_alive():
            return {"status": "ok"}
        stale = [s.name for s in watchdog.statuses() if not s.alive]
        return JSONResponse(
            status_code=503,
            content={"status": "stale", "stale": stale},
        )
