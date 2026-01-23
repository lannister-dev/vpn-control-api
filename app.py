from fastapi import FastAPI
from services.auth.router import router as auth_router
from services.nodes.router import router as node_router


app = FastAPI(
    title="VPN Control API",
    docs_url='/api/docs'
)

app.include_router(auth_router)
app.include_router(node_router)
