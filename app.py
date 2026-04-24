import logging

import uvicorn
from fastapi import APIRouter, FastAPI, status
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from prometheus_fastapi_instrumentator import Instrumentator

from shared.app.bootstrap import configure_root_logging
from shared.app.healthz import add_healthz
from shared.app.lifespan import build_lifespan
from shared.utils.logger import StructuredLogger

from services.admin_transport.router import router as admin_transport_router
from services.auth.docs import DocsBasicAuthMiddleware
from services.auth.router import router as auth_router
from services.admin_ops.router import router as admin_ops_router
from services.admin_status.runtime_service import RuntimeReadinessService
from services.admin_status.schemas import RuntimeReadinessOut
from services.admin_status.router import router as admin_status_router
from services.artifacts.router import router as artifacts_router
from services.connect.router import router as connect_router
from services.entry.router import router as entry_router
from services.admin_nodes.router import (
    admin_router as nodes_admin_router,
    installer_router as nodes_installer_router,
)
from services.nodes.router import router as node_router
from services.placements.router import router as placements_router
from services.probe.router import router as probe_router
from services.routes.router import router as routes_router
from services.auth.admin.router import router as admin_auth_router
from services.traffic.users.router import router as traffic_admin_router
from services.traffic.nodes.router import router as nodes_traffic_admin_router
from services.vpn.keys.router import router as vpn_router
from services.plans.router import router as plans_router
from services.users.router import router as users_router
from services.vpn.subscriptions.router import router as subscriptions_router
from services.billing.router import router as billing_router
from services.bot_api.router import router as bot_api_router


configure_root_logging()
logger = StructuredLogger(logging.getLogger("vpn-control-api"))

app = FastAPI(
    title="VPN Control API",
    docs_url="/api/instruction",
    openapi_url="/api/openapi.json",
    lifespan=build_lifespan(logger=logger, ready_event="api_ready", shutdown_event="api_shutdown"),
)

runtime_readiness_service = RuntimeReadinessService()

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(admin_auth_router)
api_router.include_router(auth_router)
api_router.include_router(admin_ops_router)
api_router.include_router(admin_status_router)
api_router.include_router(admin_transport_router)
api_router.include_router(artifacts_router)
api_router.include_router(connect_router)
api_router.include_router(entry_router)
api_router.include_router(node_router)
api_router.include_router(nodes_admin_router)
api_router.include_router(nodes_installer_router)
api_router.include_router(placements_router)
api_router.include_router(probe_router)
api_router.include_router(routes_router)
api_router.include_router(traffic_admin_router)
api_router.include_router(nodes_traffic_admin_router)
api_router.include_router(vpn_router)
api_router.include_router(plans_router)
api_router.include_router(users_router)
api_router.include_router(subscriptions_router)
api_router.include_router(billing_router)
api_router.include_router(bot_api_router)

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


add_healthz(app)

app.mount(
    "/api/instruction",
    StaticFiles(directory="shared/static/instruction", html=True),
    name="instruction",
)

app.add_middleware(DocsBasicAuthMiddleware)

Instrumentator().instrument(app).expose(app, endpoint="/api/monitoring")


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
