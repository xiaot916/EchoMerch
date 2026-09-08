from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import logging
from time import perf_counter

from app.api.v1.router import api_router
from app.core.local_database import LocalDatabase
from app.core.config import settings
from app.modules.access.service import AccessControlStore
from app.modules.collection.service import collection_scheduler
from app.integrations.jackyun_inventory import jackyun_inventory_scheduler


logger = logging.getLogger("echomerch.http")


def create_app() -> FastAPI:
    app = FastAPI(
        title="EchoMerch API",
        version="0.1.0",
        description="E-commerce analytics, data collection, and completeness API.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH"],
        allow_headers=["Accept", "Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def request_timing_middleware(request, call_next):
        """Expose request latency without logging query strings or credentials."""
        started = perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = (perf_counter() - started) * 1000
            logger.exception("request failed method=%s path=%s elapsed_ms=%.1f", request.method, request.url.path, elapsed_ms)
            raise
        elapsed_ms = (perf_counter() - started) * 1000
        response.headers["X-Request-Duration-Ms"] = f"{elapsed_ms:.1f}"
        if elapsed_ms >= 1000:
            logger.warning("slow request method=%s path=%s status=%s elapsed_ms=%.1f", request.method, request.url.path, response.status_code, elapsed_ms)
        else:
            logger.info("request method=%s path=%s status=%s elapsed_ms=%.1f", request.method, request.url.path, response.status_code, elapsed_ms)
        return response

    app.include_router(api_router, prefix="/api/v1")

    @app.on_event("startup")
    def initialize_local_database() -> None:
        LocalDatabase(Path(settings.local_database_path)).initialize_schema()
        AccessControlStore(Path(settings.local_database_path)).ensure_default_admin()
        collection_scheduler.start()
        jackyun_inventory_scheduler.start()

    @app.on_event("shutdown")
    def stop_collection_scheduler() -> None:
        collection_scheduler.stop()
        jackyun_inventory_scheduler.stop()

    return app


app = create_app()
