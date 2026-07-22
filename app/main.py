"""Ponto de entrada da aplicacao FastAPI: ciclo de vida, middlewares e rotas."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.api.routes import cnpj, health, webhook
from app.config.settings import get_settings
from app.core.exceptions import AppError
from app.core.logging import configure_logging
from app.core.security import mask_webhook_url
from app.db.session import create_engine, create_session_factory, init_models
from app.services.idempotency import DealLockRegistry

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Inicializa recursos compartilhados (HTTP client, banco, locks) e os libera ao encerrar."""
    settings = get_settings()
    configure_logging(settings.log_level)

    logger.info(
        "Iniciando aplicacao. Webhook Bitrix: %s | CNPJa base: %s",
        mask_webhook_url(settings.bitrix_webhook_base_url),
        settings.cnpja_base_url,
    )

    http_client = httpx.AsyncClient(timeout=settings.http_timeout_seconds)
    engine = create_engine(settings.database_url)
    await init_models(engine)
    session_factory = create_session_factory(engine)

    app.state.http_client = http_client
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.lock_registry = DealLockRegistry()

    try:
        yield
    finally:
        await http_client.aclose()
        await engine.dispose()
        logger.info("Aplicacao encerrada.")


def create_app() -> FastAPI:
    """Cria e configura a instancia da aplicacao FastAPI."""
    app = FastAPI(
        title="Integracao Bitrix24 <-> CNPJa",
        description="API interna que enriquece Negocios do Bitrix24 com dados publicos da CNPJa.",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.include_router(health.router)
    app.include_router(cnpj.router)
    app.include_router(webhook.router)

    @app.exception_handler(AppError)
    async def _integration_error_handler(request: Request, exc: AppError) -> JSONResponse:
        """Fallback para excecoes de dominio nao tratadas explicitamente nas rotas."""
        logger.warning("Erro de integracao nao tratado na rota: %s", type(exc).__name__)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": exc.message},
        )

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Garante que nenhum stack trace seja exposto ao cliente em erros nao previstos."""
        if isinstance(exc, HTTPException):
            raise exc
        logger.exception("Erro interno nao previsto.")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Erro interno nao previsto."},
        )

    return app


app = create_app()
