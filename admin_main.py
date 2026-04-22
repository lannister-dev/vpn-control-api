import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, APIRouter
from prometheus_fastapi_instrumentator import Instrumentator
from starlette.staticfiles import StaticFiles

from shared.database.session import AsyncDatabase
from shared.nats.client import NatsClient
from shared.profiles.init import bootstrap_profiles_registry
from shared.redis.client import redis_client
from shared.utils.logger import StructuredLogger
from services.config import get_settings

# Admin UI (panel + static)
from services.admin_ui.router import router as admin_ui_router, STATIC_DIR
from services.admin_ui.router_v2 import router as admin_ui_v2_router, STATIC_V2_DIR

# Admin API routers used by the panel frontend
from services.auth.admin.router import router as admin_auth_router
from services.admin_ops.router import router as admin_ops_router
from services.admin_status.router import router as admin_status_router
from services.admin_transport.router import router as admin_transport_router
from services.admin_nodes.router import (
    admin_router as nodes_admin_router,
    installer_router as nodes_installer_router,
)
from services.entry.router import router as entry_router
from services.nodes.router import router as node_router
from services.placements.router import router as placements_router
from services.probe.router import router as probe_router
from services.routes.router import router as routes_router
from services.traffic.users.router import router as traffic_admin_router
from services.traffic.nodes.router import router as nodes_traffic_admin_router
from services.plans.router import router as plans_router
from services.zones.router import router as zones_router
from services.users.router import router as users_router
from services.vpn.subscriptions.router import router as subscriptions_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = StructuredLogger(logging.getLogger("admin-panel"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    await redis_client.connect()
    log.info("redis_connected")

    session_maker = AsyncDatabase.get_session_maker()
    async with session_maker() as session:
        await bootstrap_profiles_registry(session)

    settings = get_settings()
    nats_client: NatsClient | None = None
    if settings.nats.enabled:
        nats_client = NatsClient(settings.nats)
        try:
            await nats_client.connect()
            app.state.nats_client = nats_client
            app.state.nats_config = settings.nats
            log.info("admin_nats_connected")
        except Exception as exc:
            log.exception("admin_nats_connect_failed", error=str(exc))
            nats_client = None

    log.info("admin_panel_ready")
    try:
        yield
    finally:
        if nats_client is not None:
            try:
                await nats_client.close()
            except Exception:
                log.exception("admin_nats_close_failed")
        log.info("admin_panel_shutdown")


app = FastAPI(
    title="VPN Control Admin Panel",
    docs_url=None,
    openapi_url=None,
    lifespan=lifespan,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(admin_auth_router)
api_router.include_router(admin_ops_router)
api_router.include_router(admin_status_router)
api_router.include_router(admin_transport_router)
api_router.include_router(nodes_admin_router)
api_router.include_router(nodes_installer_router)
api_router.include_router(entry_router)
api_router.include_router(node_router)
api_router.include_router(placements_router)
api_router.include_router(probe_router)
api_router.include_router(routes_router)
api_router.include_router(traffic_admin_router)
api_router.include_router(nodes_traffic_admin_router)
api_router.include_router(plans_router)
api_router.include_router(zones_router)
api_router.include_router(users_router)
api_router.include_router(subscriptions_router)

app.include_router(api_router)

# Panel at root, static at /static
app.include_router(admin_ui_router)
app.include_router(admin_ui_v2_router)
if STATIC_V2_DIR.exists():
    app.mount("/static/v2", StaticFiles(directory=str(STATIC_V2_DIR)), name="admin-static-v2")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="admin-static")

Instrumentator().instrument(app).expose(app, endpoint="/api/monitoring")


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run("admin_main:app", host="0.0.0.0", port=8082)
