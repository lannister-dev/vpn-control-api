import logging

import uvicorn
from fastapi import APIRouter, FastAPI
from prometheus_fastapi_instrumentator import Instrumentator
from starlette.staticfiles import StaticFiles

from services.admin_audit.router import router as admin_audit_router
from services.admin_nodes.router import (
    admin_router as nodes_admin_router,
)
from services.admin_nodes.router import (
    installer_router as nodes_installer_router,
)
from services.admin_ops.router import router as admin_ops_router
from services.admin_status.router import router as admin_status_router
from services.admin_transport.policy.router import router as admin_transport_policy_router
from services.admin_transport.router import router as admin_transport_router
from services.admin_ui.router_v2 import STATIC_V2_DIR
from services.admin_ui.router_v2 import router as admin_ui_v2_router
from services.alerts.admin_router import router as admin_alerts_router
from services.auth.admin.router import router as admin_auth_router
from services.config import get_settings
from services.entry.router import router as entry_router
from services.nodes.policy.router import router as node_policy_router
from services.nodes.router import router as node_router
from services.placements.router import router as placements_router
from services.plans.router import router as plans_router
from services.probe.policy.router import router as probe_policy_router
from services.probe.router import router as probe_router
from services.routes.router import router as routes_router
from services.routing.entry.router import router as entry_routing_admin_router
from services.traffic.nodes.router import router as nodes_traffic_admin_router
from services.traffic.policy.router import router as traffic_policy_router
from services.traffic.users.router import router as traffic_admin_router
from services.users.router import router as users_router
from services.vpn.subscriptions.router import router as subscriptions_router
from services.zones.router import router as zones_router
from shared.app.bootstrap import configure_root_logging
from shared.app.healthz import add_healthz
from shared.app.lifespan import build_lifespan
from shared.middlewares.request_id import add_request_id_middleware
from shared.utils.logger import StructuredLogger

configure_root_logging()
logger = StructuredLogger(logging.getLogger("admin-panel"))

settings = get_settings()

app = FastAPI(
    title="VPN Control Admin Panel",
    docs_url=None,
    openapi_url=None,
    lifespan=build_lifespan(
        logger=logger,
        with_nats=settings.nats.enabled,
        nats_settings=settings.nats,
        ready_event="admin_panel_ready",
        shutdown_event="admin_panel_shutdown",
    ),
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(admin_auth_router)
api_router.include_router(admin_ops_router)
api_router.include_router(admin_status_router)
api_router.include_router(admin_transport_router)
api_router.include_router(admin_transport_policy_router)
api_router.include_router(nodes_admin_router)
api_router.include_router(nodes_installer_router)
api_router.include_router(entry_router)
api_router.include_router(node_router)
api_router.include_router(placements_router)
api_router.include_router(probe_router)
api_router.include_router(probe_policy_router)
api_router.include_router(node_policy_router)
api_router.include_router(admin_audit_router)
api_router.include_router(admin_alerts_router)
api_router.include_router(routes_router)
api_router.include_router(traffic_admin_router)
api_router.include_router(nodes_traffic_admin_router)
api_router.include_router(traffic_policy_router)
api_router.include_router(entry_routing_admin_router)
api_router.include_router(plans_router)
api_router.include_router(zones_router)
api_router.include_router(users_router)
api_router.include_router(subscriptions_router)

app.include_router(api_router)

add_request_id_middleware(app)

Instrumentator().instrument(app).expose(app, endpoint="/api/monitoring")

add_healthz(app)

if STATIC_V2_DIR.exists():
    app.mount("/static/v2", StaticFiles(directory=str(STATIC_V2_DIR)), name="admin-static-v2")
# SPA catchall — must be registered LAST so specific routes match first.
app.include_router(admin_ui_v2_router)


if __name__ == "__main__":
    uvicorn.run("admin_main:app", host="0.0.0.0", port=8082)
