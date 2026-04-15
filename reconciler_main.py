import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from shared.database.session import AsyncDatabase
from shared.profiles.init import bootstrap_profiles_registry
from shared.redis.client import redis_client
from shared.utils.logger import StructuredLogger
from services.config import get_settings

from services.nodes.reconciler import NodePlacementReconciler
from services.nodes.agent.runtime import NodeAgentRuntime
from services.probe.cleanup_reconciler import ProbeSignalCleanupReconciler
from services.probe.reconciler import ProbeAutoDrainReconciler
from services.probe.synthetic_reconciler import ProbeSyntheticCredentialReconciler
from services.routes.reconciler import RouteWarmupReconciler
from services.traffic.consumer import UserTrafficNatsConsumer
from services.traffic.reconciler import TrafficHistoryCleanupReconciler
from services.traffic.reset_reconciler import TrafficResetReconciler
from services.admin_transport.cleanup_reconciler import AdminTransportCleanupReconciler
from services.placements.error_retry_reconciler import PlacementErrorRetryReconciler
from services.placements.reconciler import PlacementRebalanceReconciler
from services.vpn.keys.expiration_reconciler import VpnKeyExpirationReconciler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = StructuredLogger(logging.getLogger("reconciler-worker"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    await redis_client.connect()
    log.info("redis_connected")

    session_maker = AsyncDatabase.get_session_maker()
    async with session_maker() as session:
        await bootstrap_profiles_registry(session)

    settings = get_settings()

    reconcilers = [
        RouteWarmupReconciler(),
        ProbeSignalCleanupReconciler(),
        ProbeAutoDrainReconciler(),
        ProbeSyntheticCredentialReconciler(),
        NodePlacementReconciler(),
        TrafficHistoryCleanupReconciler(),
        AdminTransportCleanupReconciler(),
        TrafficResetReconciler(),
        PlacementErrorRetryReconciler(),
        PlacementRebalanceReconciler(),
        VpnKeyExpirationReconciler(),
    ]
    runtimes = [
        NodeAgentRuntime(settings.nats),
        UserTrafficNatsConsumer(settings.nats),
    ]

    for r in reconcilers:
        await r.start()
    for r in runtimes:
        await r.start()

    log.info("all_reconcilers_started", count=len(reconcilers) + len(runtimes))

    try:
        yield
    finally:
        for r in reversed(runtimes):
            await r.stop()
        for r in reversed(reconcilers):
            await r.stop()
        log.info("all_reconcilers_stopped")


app = FastAPI(docs_url=None, openapi_url=None, lifespan=lifespan)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run("reconciler_main:app", host="0.0.0.0", port=8081)
