"""Testes de integracao da rota de compatibilidade POST /webhook/bitrix/enriquecer-cnpj."""

import httpx
import pytest

from tests.integration.conftest import INTEGRATION_API_KEY
from tests.integration.test_enrich_deal import (
    CNPJ_VALIDO,
    DEAL_ID,
    _bitrix_handler_padrao,
    _cnpja_handler_padrao,
)

WEBHOOK_PATH = "/webhook/bitrix/enriquecer-cnpj"


@pytest.fixture
def bitrix_handler():
    return _bitrix_handler_padrao()


@pytest.fixture
def cnpja_handler():
    return _cnpja_handler_padrao()


def _set_bitrix_handler(app_client: httpx.AsyncClient, handler) -> None:
    app_client._transport.app.state.bitrix_handler_box.handler = handler  # type: ignore[attr-defined]


async def test_webhook_chamada_valida_retorna_200_e_reaproveita_servico(app_client: httpx.AsyncClient) -> None:
    resposta = await app_client.post(
        WEBHOOK_PATH,
        params={"token": INTEGRATION_API_KEY, "dealId": DEAL_ID},
    )
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["success"] is True
    assert corpo["deal_id"] == DEAL_ID
    assert corpo["cnpj"] == CNPJ_VALIDO
    assert corpo["dry_run"] is False
    assert "razao_social" in corpo["fields_changed"]
    assert corpo["source"] == "CNPJá API Pública"


async def test_webhook_token_invalido_retorna_401(app_client: httpx.AsyncClient) -> None:
    resposta = await app_client.post(
        WEBHOOK_PATH,
        params={"token": "token-errado", "dealId": DEAL_ID},
    )
    assert resposta.status_code == 401


async def test_webhook_token_ausente_retorna_422_por_parametro_obrigatorio(app_client: httpx.AsyncClient) -> None:
    # "token" e query obrigatoria: FastAPI retorna 422 quando o parametro esta ausente
    resposta = await app_client.post(WEBHOOK_PATH, params={"dealId": DEAL_ID})
    assert resposta.status_code == 422


async def test_webhook_token_vazio_retorna_401(app_client: httpx.AsyncClient) -> None:
    # token enviado, porem vazio: passa pela validacao de presenca do FastAPI, mas falha na comparacao
    resposta = await app_client.post(
        WEBHOOK_PATH,
        params={"token": "", "dealId": DEAL_ID},
    )
    assert resposta.status_code == 401


async def test_webhook_deal_id_invalido_retorna_422(app_client: httpx.AsyncClient) -> None:
    resposta = await app_client.post(
        WEBHOOK_PATH,
        params={"token": INTEGRATION_API_KEY, "dealId": -1},
    )
    assert resposta.status_code == 422


async def test_webhook_deal_id_nao_numerico_retorna_422(app_client: httpx.AsyncClient) -> None:
    resposta = await app_client.post(
        WEBHOOK_PATH,
        params={"token": INTEGRATION_API_KEY, "dealId": "abc"},
    )
    assert resposta.status_code == 422


async def test_webhook_dry_run_nao_atualiza_mas_reporta_diferencas(app_client: httpx.AsyncClient) -> None:
    def bitrix_sem_update(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("crm.deal.update.json"):
            raise AssertionError("dryRun=true nao deveria chamar crm.deal.update")
        return _bitrix_handler_padrao()(request)

    _set_bitrix_handler(app_client, bitrix_sem_update)

    resposta = await app_client.post(
        WEBHOOK_PATH,
        params={"token": INTEGRATION_API_KEY, "dealId": DEAL_ID, "dryRun": "true"},
    )
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["dry_run"] is True
    assert "razao_social" in corpo["fields_changed"]


async def test_webhook_force_ignora_sincronizacao_recente(app_client: httpx.AsyncClient) -> None:
    chamadas_cnpja = 0

    def cnpja_contador(request: httpx.Request) -> httpx.Response:
        nonlocal chamadas_cnpja
        chamadas_cnpja += 1
        return _cnpja_handler_padrao()(request)

    app_client._transport.app.state.cnpja_handler_box.handler = cnpja_contador  # type: ignore[attr-defined]

    primeira = await app_client.post(
        WEBHOOK_PATH,
        params={"token": INTEGRATION_API_KEY, "dealId": DEAL_ID},
    )
    assert primeira.status_code == 200
    assert chamadas_cnpja == 1

    segunda_sem_force = await app_client.post(
        WEBHOOK_PATH,
        params={"token": INTEGRATION_API_KEY, "dealId": DEAL_ID},
    )
    assert segunda_sem_force.status_code == 200
    # sem force, a sincronizacao recente e reaproveitada: nao consulta a CNPJa de novo
    assert chamadas_cnpja == 1

    terceira_com_force = await app_client.post(
        WEBHOOK_PATH,
        params={"token": INTEGRATION_API_KEY, "dealId": DEAL_ID, "force": "true"},
    )
    assert terceira_com_force.status_code == 200
    # com force=true, a CNPJa deve ser consultada novamente
    assert chamadas_cnpja == 2


async def test_webhook_nao_registra_token_na_resposta_de_erro(app_client: httpx.AsyncClient) -> None:
    token_secreto = "token-que-nao-pode-vazar"
    resposta = await app_client.post(
        WEBHOOK_PATH,
        params={"token": token_secreto, "dealId": DEAL_ID},
    )
    assert resposta.status_code == 401
    assert token_secreto not in resposta.text


async def test_webhook_rota_aparece_no_openapi(app_client: httpx.AsyncClient) -> None:
    resposta = await app_client.get("/openapi.json")
    assert resposta.status_code == 200
    schema = resposta.json()
    assert WEBHOOK_PATH in schema["paths"]
    assert "post" in schema["paths"][WEBHOOK_PATH]
