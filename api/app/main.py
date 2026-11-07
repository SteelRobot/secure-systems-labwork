import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from . import config
from .cache import r as redis_client
from .db import pool

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
    # Подробности (стек, текст исключения) – только в журнал; клиенту – нейтральный ответ
    log.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/api/health")
def health():
    """Служебный эндпоинт состояния (в ЛР №2 не описан – см. docs/DIVERGENCES.md)."""
    with pool.connection() as conn:
        conn.execute("SELECT 1")
    redis_client.ping()
    return {"status": "ok"}


# Эндпоинты по контракту ЛР №2 подключаются здесь, по одному:
# from .routers import auth, applications, ...
# app.include_router(auth.router)
