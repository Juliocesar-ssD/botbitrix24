"""Testes do CnpjaClient: rate limit local, HTTP 429, timeout e nao repeticao de 404."""

import httpx
import pytest

from app.clients.cnpja import CnpjaClient
from app.core.exceptions import CnpjaApiError, CnpjaNotFoundError, CnpjaRateLimitError

CNPJ_VALIDO = "00000000000191"

_PAYLOAD_OFFICE_VALIDO = {
    "taxId": CNPJ_VALIDO,
    "alias": "Nome Fantasia",
    "founded": "1990-01-01",
    "head": True,
    "statusDate": "2020-01-01",
    "status": {"id": 1, "text": "Ativa"},
    "address": {"state": "RJ", "street": "Rua X", "zip": "20000000"},
    "mainActivity": {"id": 123, "text": "Atividade"},
    "company": {"name": "Empresa Exemplo", "equity": 1000.0, "members": []},
}


def _client_com_transport(handler: httpx.MockTransport, max_per_minute: int = 5) -> CnpjaClient:
    http_client = httpx.AsyncClient(transport=handler)
    return CnpjaClient("https://open.cnpja.com", http_client, max_requests_per_minute=max_per_minute)


async def test_get_office_sucesso() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_PAYLOAD_OFFICE_VALIDO, headers={"content-type": "application/json"})

    client = _client_com_transport(httpx.MockTransport(handler))
    resultado = await client.get_office(CNPJ_VALIDO)
    assert resultado.taxId == CNPJ_VALIDO
    assert resultado.company is not None
    assert resultado.company.name == "Empresa Exemplo"


async def test_get_office_404_nao_repete_e_levanta_not_found() -> None:
    chamadas = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal chamadas
        chamadas += 1
        return httpx.Response(404, json={"message": "not found"})

    client = _client_com_transport(httpx.MockTransport(handler))
    with pytest.raises(CnpjaNotFoundError):
        await client.get_office(CNPJ_VALIDO)
    assert chamadas == 1


async def test_get_office_400_nao_repete() -> None:
    chamadas = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal chamadas
        chamadas += 1
        return httpx.Response(400, json={"message": "bad request"})

    client = _client_com_transport(httpx.MockTransport(handler))
    with pytest.raises(CnpjaApiError):
        await client.get_office(CNPJ_VALIDO)
    assert chamadas == 1


async def test_get_office_429_respeita_retry_after_e_levanta_apos_max_tentativas() -> None:
    chamadas = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal chamadas
        chamadas += 1
        return httpx.Response(429, json={"message": "rate limited"}, headers={"retry-after": "0.01"})

    client = _client_com_transport(httpx.MockTransport(handler))
    with pytest.raises(CnpjaRateLimitError):
        await client.get_office(CNPJ_VALIDO)
    assert chamadas == 3


async def test_get_office_timeout_levanta_erro_apos_tentativas() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timeout simulado", request=request)

    client = _client_com_transport(httpx.MockTransport(handler))
    with pytest.raises(CnpjaApiError):
        await client.get_office(CNPJ_VALIDO)


async def test_get_office_content_type_invalido_levanta_erro() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>nao e json</html>", headers={"content-type": "text/html"})

    client = _client_com_transport(httpx.MockTransport(handler))
    with pytest.raises(CnpjaApiError):
        await client.get_office(CNPJ_VALIDO)


async def test_rate_limiter_local_limita_a_cinco_por_minuto() -> None:
    """Com limite de 2 req/min, a terceira chamada precisa aguardar a janela deslizante liberar."""
    import asyncio
    import time

    chamadas_timestamps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        chamadas_timestamps.append(time.monotonic())
        return httpx.Response(200, json=_PAYLOAD_OFFICE_VALIDO, headers={"content-type": "application/json"})

    client = _client_com_transport(httpx.MockTransport(handler), max_per_minute=2)

    # dispara 2 chamadas: devem ser imediatas, pois ha vaga na janela
    await asyncio.wait_for(asyncio.gather(client.get_office(CNPJ_VALIDO), client.get_office(CNPJ_VALIDO)), timeout=2)
    assert len(chamadas_timestamps) == 2
    # a diferenca entre as duas primeiras chamadas deve ser pequena (sem espera)
    assert (chamadas_timestamps[1] - chamadas_timestamps[0]) < 1.0
