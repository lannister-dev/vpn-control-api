import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, APIRouter
from prometheus_fastapi_instrumentator import Instrumentator
from shared.database.session import AsyncDatabase
from shared.profiles.init import bootstrap_profiles_registry
from shared.redis.client import redis_client
from shared.utils.logger import StructuredLogger

from services.auth.docs import DocsBasicAuthMiddleware
from services.auth.router import router as auth_router
from services.admin_status.router import router as admin_status_router
from services.artifacts.router import router as artifacts_router
from services.backend_peers.router import router as backend_peers_router
from services.connect.router import router as connect_router
from services.nodes.router import router as node_router
from services.placements.router import router as placements_router
from services.probe.router import router as probe_router
from services.vpn.keys.router import router as vpn_router
from services.vpn.subscriptions.router import router as subscriptions_router


log = StructuredLogger(logging.getLogger("vpn-control-api"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Redis
    await redis_client.connect()
    log.info("Redis initialized")

    # Profiles registry (DB artifacts)
    session_maker = AsyncDatabase.get_session_maker()
    async with session_maker() as session:
        await bootstrap_profiles_registry(session)
    yield
    log.info("Application shutdown")


app = FastAPI(
    title="VPN Control API",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# Routers
api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router)
api_router.include_router(admin_status_router)
api_router.include_router(artifacts_router)
api_router.include_router(backend_peers_router)
api_router.include_router(connect_router)
api_router.include_router(node_router)
api_router.include_router(placements_router)
api_router.include_router(probe_router)
api_router.include_router(vpn_router)
api_router.include_router(subscriptions_router)

app.include_router(api_router)

app.add_middleware(DocsBasicAuthMiddleware)

Instrumentator().instrument(app).expose(app, endpoint="/api/monitoring")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
