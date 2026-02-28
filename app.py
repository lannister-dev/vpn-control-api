import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import APIRouter, FastAPI, status
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from services.admin_ops.router import router as admin_ops_router
from services.admin_status.router import router as admin_status_router
from services.admin_status.runtime_service import RuntimeReadinessService
from services.admin_status.schemas import RuntimeReadinessOut
from services.admin_ui.router import router as admin_ui_router
from services.artifacts.router import router as artifacts_router
from services.auth.docs import DocsBasicAuthMiddleware
from services.auth.router import router as auth_router
from services.connect.router import router as connect_router
from services.nodes.reconciler import NodePlacementReconciler
from services.nodes.router import router as node_router
from services.placements.router import router as placements_router
from services.probe.reconciler import ProbeAutoDrainReconciler
from services.probe.router import router as probe_router
from services.routes.reconciler import RouteWarmupReconciler
from services.routes.router import router as routes_router
from services.vpn.keys.router import router as vpn_router
from services.vpn.subscriptions.router import router as subscriptions_router
from services.xray_stats_collector import init_xray_clients
from services.xray_stats_collector import router as xray_stats_router
from shared.database.session import AsyncDatabase
from shared.profiles.init import bootstrap_profiles_registry
from shared.redis.client import redis_client
from shared.utils.logger import StructuredLogger

log = StructuredLogger(logging.getLogger("vpn-control-api"))


def _get_xray_nodes_config() -> dict[str, tuple[str, int]]:
    """Load XRay nodes configuration from environment variables."""

    nodes = {
        "fi-1": ("45.38.228.66", 10085),  # Your first X-ray node
        "fr-1": ("217.60.60.39", 10085),  # Your second X-ray node
    }

    return nodes


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Redis
    await redis_client.connect()
    log.info("Redis initialized")

    # Profiles registry (DB artifacts)
    session_maker = AsyncDatabase.get_session_maker()
    async with session_maker() as session:
        await bootstrap_profiles_registry(session)

    warmup_reconciler = RouteWarmupReconciler()
    probe_auto_drain_reconciler = ProbeAutoDrainReconciler()
    node_auto_heal_reconciler = NodePlacementReconciler()

    try:
        xray_nodes = _get_xray_nodes_config()
        xray_timeout = int(os.getenv("XRAY_TIMEOUT_S", "5"))
        init_xray_clients(xray_nodes, timeout_s=xray_timeout)
        log.info(
            "XRay stats collector initialized",
            nodes=list(xray_nodes.keys()),
            timeout_s=xray_timeout,
        )
    except Exception as e:
        log.warning("Failed to initialize XRay stats collector", error=str(e))

    await warmup_reconciler.start()
    await probe_auto_drain_reconciler.start()
    await node_auto_heal_reconciler.start()
    try:
        yield
    finally:
        await node_auto_heal_reconciler.stop()
        await probe_auto_drain_reconciler.stop()
        await warmup_reconciler.stop()
    log.info("Application shutdown")


app = FastAPI(
    title="VPN Control API",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)
runtime_readiness_service = RuntimeReadinessService()

# Routers
api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router)
api_router.include_router(admin_ops_router)
api_router.include_router(admin_status_router)
api_router.include_router(admin_ui_router)
api_router.include_router(artifacts_router)
api_router.include_router(connect_router)
api_router.include_router(node_router)
api_router.include_router(placements_router)
api_router.include_router(probe_router)
api_router.include_router(routes_router)
api_router.include_router(vpn_router)
api_router.include_router(subscriptions_router)
api_router.include_router(xray_stats_router)

app.include_router(api_router)


@app.get(
    "/api/readyz",
    response_model=RuntimeReadinessOut,
    include_in_schema=False,
)
async def runtime_readiness() -> RuntimeReadinessOut | JSONResponse:
    readiness = await runtime_readiness_service.get_readiness()
    if readiness.ready:
        return readiness
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content=readiness.model_dump(mode="json"),
    )


app.add_middleware(DocsBasicAuthMiddleware)

Instrumentator().instrument(app).expose(app, endpoint="/api/monitoring")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
