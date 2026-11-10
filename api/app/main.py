import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from . import config
from .cache import r as redis_client
from .db import pool
from .routers import auth, applications, reports

logging.basicConfig(level=config.LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("api")

@asynccontextmanager
async def lifespan(app: FastAPI):
    pool.open()
    yield
    pool.close()

app = FastAPI(
    title="Support system API", lifespan=lifespan,
    docs_url="/api/docs" if config.API_DOCS_ENABLED else None,
    redoc_url=None, openapi_url="/api/openapi.json" if config.API_DOCS_ENABLED else None,
)

@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})

@app.get("/api/health")
def health():
    with pool.connection() as conn:
        conn.execute("SELECT 1")
    redis_client.ping()
    return {"status": "ok"}

# Подключение роутеров
app.include_router(auth.router)
app.include_router(applications.router)
app.include_router(reports.router)
