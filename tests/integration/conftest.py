"""Fixtures compartilhadas dos testes de integracao: app FastAPI com dependencias mockadas."""

import os
from collections.abc import AsyncGenerator, Callable

import httpx
import pytest
from fastapi import FastAPI

os.environ.setdefault("BITRIX_WEBHOOK_BASE_URL", "https://portal.bitrix24.com.br/rest/1/token-de-teste")
os.environ.setdefault("INTEGRATION_API_KEY", "chave-de-teste-integracao")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from app.clients.bitrix import BitrixClient  # noqa: E402
from app.clients.cnpja import CnpjaClient  # noqa: E402
from app.config.settings import get_settings  # noqa: E402
from app.db.session import create_engine, create_session_factory, init_models  # noqa: E402
from app.main import create_app  # noqa: E402
from app.services.idempotency import DealLockRegistry  # noqa: E402

INTEGRATION_API_KEY = "chave-de-teste-integracao"

BitrixHandler = Callable[[httpx.Request], httpx.Response]
CnpjaHandler = Callable[[httpx.Request], httpx.Response]


class MutableHandlerBox:
    """Permite trocar o handler do MockTransport em tempo de execucao, dentro do mesmo teste.

    O httpx.MockTransport guarda uma referencia fixa a funcao no momento da construcao;
    encapsulando a chamada indireta aqui, um teste pode reatribuir `.handler` a qualquer
    momento (ex: simular uma segunda chamada com resposta diferente) sem recriar o client.
    """

    def __init__(self, handler: BitrixHandler | CnpjaHandler) -> None:
        self.handler = handler

    def __call__(self, request: httpx.Request) -> httpx.Response:
        return self.handler(request)


@pytest.fixture
def bitrix_handler() -> BitrixHandler:
    """Handler padrao do Bitrix: sobrescrito nos testes que precisam de comportamento especifico."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("bitrix_handler nao configurado para este teste")

    return handler


@pytest.fixture
def cnpja_handler() -> CnpjaHandler:
    """Handler padrao da CNPJa: sobrescrito nos testes que precisam de comportamento especifico."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("cnpja_handler nao configurado para este teste")

    return handler


@pytest.fixture
async def app_client(
    bitrix_handler: BitrixHandler, cnpja_handler: CnpjaHandler
) -> AsyncGenerator[httpx.AsyncClient]:
    """Sobe a aplicacao FastAPI real, mas com Bitrix/CNPJa substituidos por MockTransport."""
    app: FastAPI = create_app()
    settings = get_settings()

    bitrix_box = MutableHandlerBox(bitrix_handler)
    cnpja_box = MutableHandlerBox(cnpja_handler)

    bitrix_http_client = httpx.AsyncClient(transport=httpx.MockTransport(bitrix_box))
    cnpja_http_client = httpx.AsyncClient(transport=httpx.MockTransport(cnpja_box))

    engine = create_engine("sqlite+aiosqlite:///:memory:")
    await init_models(engine)
    session_factory = create_session_factory(engine)

    # substitui os recursos que o lifespan normalmente criaria por versoes isoladas para o teste
    app.state.bitrix_client = BitrixClient(settings.bitrix_webhook_base_url, bitrix_http_client)
    app.state.cnpja_client = CnpjaClient(
        settings.cnpja_base_url, cnpja_http_client, settings.max_cnpja_requests_per_minute
    )
    app.state.session_factory = session_factory
    app.state.lock_registry = DealLockRegistry()
    app.state.http_client = bitrix_http_client
    # expostos para que um teste possa trocar o comportamento simulado em tempo de execucao
    app.state.bitrix_handler_box = bitrix_box
    app.state.cnpja_handler_box = cnpja_box

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client

    await bitrix_http_client.aclose()
    await cnpja_http_client.aclose()
    await engine.dispose()
