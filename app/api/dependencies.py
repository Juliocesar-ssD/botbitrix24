"""Dependencias compartilhadas das rotas: settings, clients, sessao de banco e seguranca."""

import uuid
from collections.abc import AsyncGenerator
from typing import Annotated

import httpx
from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clients.bitrix import BitrixClient
from app.clients.cnpja import CnpjaClient
from app.config.settings import Settings, get_settings
from app.core.security import constant_time_compare
from app.services.idempotency import DealLockRegistry


def get_app_settings() -> Settings:
    """Fornece a instancia cacheada de configuracoes."""
    return get_settings()


async def require_integration_key(
    settings: Annotated[Settings, Depends(get_app_settings)],
    x_integration_key: Annotated[str | None, Header()] = None,
) -> None:
    """Exige o header X-Integration-Key valido, comparado em tempo constante."""
    # ausencia do header e tratada como chave invalida
    if not x_integration_key or not constant_time_compare(x_integration_key, settings.integration_api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Integration-Key invalida ou ausente.",
        )


def get_request_id(request: Request) -> str:
    """Gera (ou reaproveita) um identificador de requisicao para correlacionar logs."""
    # reaproveita um request-id ja existente no header, se enviado pelo chamador
    existente = request.headers.get("x-request-id")
    if existente:
        return existente
    # gera um novo identificador aleatorio para esta requisicao
    return str(uuid.uuid4())


def get_http_client(request: Request) -> httpx.AsyncClient:
    """Recupera o cliente HTTP assincrono compartilhado, criado no ciclo de vida da aplicacao."""
    return request.app.state.http_client  # type: ignore[no-any-return]


def get_bitrix_client(
    request: Request,
    http_client: Annotated[httpx.AsyncClient, Depends(get_http_client)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> BitrixClient:
    """Constroi (ou reaproveita) o BitrixClient para esta requisicao."""
    if not hasattr(request.app.state, "bitrix_client"):
        request.app.state.bitrix_client = BitrixClient(settings.bitrix_webhook_base_url, http_client)
    return request.app.state.bitrix_client  # type: ignore[no-any-return]


def get_cnpja_client(
    request: Request,
    http_client: Annotated[httpx.AsyncClient, Depends(get_http_client)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> CnpjaClient:
    """Constroi (ou reaproveita) o CnpjaClient para esta requisicao."""
    if not hasattr(request.app.state, "cnpja_client"):
        request.app.state.cnpja_client = CnpjaClient(
            settings.cnpja_base_url, http_client, settings.max_cnpja_requests_per_minute
        )
    return request.app.state.cnpja_client  # type: ignore[no-any-return]


def get_session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    """Recupera a fabrica de sessoes de banco, criada no ciclo de vida da aplicacao."""
    return request.app.state.session_factory  # type: ignore[no-any-return]


def get_lock_registry(request: Request) -> DealLockRegistry:
    """Recupera o registro de locks por deal_id, compartilhado durante toda a vida da aplicacao."""
    return request.app.state.lock_registry  # type: ignore[no-any-return]


async def get_db_session(
    session_factory: Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)],
) -> AsyncGenerator[AsyncSession]:
    """Fornece uma sessao de banco por requisicao."""
    async with session_factory() as session:
        yield session
