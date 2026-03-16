from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.router import api_router
from app.core.logging import setup_logging
from app.core.config import settings
from app.db.ensure_sqlite_schema import ensure_sqlite_schema

def create_app() -> FastAPI:
    setup_logging()
    app = FastAPI()
    if settings.app_env in {"dev", "test"}:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    ensure_sqlite_schema()
    app.include_router(api_router)
    return app

app = create_app()
