import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config import get_settings
from app.logging_config import configure_logging
from app.routes import router

configure_logging()
logger = logging.getLogger("clip.api")


class HealthResponse(BaseModel):
    status: str


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    get_settings().ensure_production_secrets()
    logger.info("api_started")
    yield
    logger.info("api_stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(title="Clip Studio API", lifespan=lifespan)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Range", "Accept-Ranges", "Content-Length"],
    )
    application.include_router(router)

    @application.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok")

    return application


app = create_app()
