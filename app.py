import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, APIRouter
from prometheus_fastapi_instrumentator import Instrumentator
from shared.database.session import AsyncDatabase
from shared.profiles.init import bootstrap_profiles_registry
from shared.redis.client import redis_client
from shared.utils.logger import StructuredLogger

from services.auth.router import router as auth_router
from services.artifacts.router import router as artifacts_router
from services.nodes.router import router as node_router
from services.vpn.keys.router import router as vpn_router


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
api_router.include_router(artifacts_router)
api_router.include_router(node_router)
api_router.include_router(vpn_router)

app.include_router(api_router)


Instrumentator().instrument(app).expose(app, endpoint="/api/metrics")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
