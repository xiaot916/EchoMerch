from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

from app.api.v1.router import api_router
from app.core.local_database import LocalDatabase
from app.core.config import settings
from app.modules.access.service import AccessControlStore
from app.modules.collection.service import collection_scheduler
from app.integrations.jackyun_inventory import jackyun_inventory_scheduler


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
