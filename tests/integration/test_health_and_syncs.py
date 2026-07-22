"""Testes de integracao de GET /health e GET /api/v1/cnpj/syncs/{deal_id}."""

import httpx

from app.config.bitrix_fields import BITRIX_FIELDS
from tests.integration.conftest import INTEGRATION_API_KEY

CNPJ_VALIDO = "00000000000191"
CNPJ_FORMATADO = "00.000.000/0001-91"
DEAL_ID = 61229

_DEAL_ATUAL = {
    "ID": str(DEAL_ID),
    BITRIX_FIELDS["cnpj"]: CNPJ_FORMATADO,
}

_ITEMS_LISTAS_VAZIAS = {
    nome: {"type": "enumeration", "title": nome, "items": []}
    for nome in (
        BITRIX_FIELDS["tipo_pessoa"],
        BITRIX_FIELDS["situacao_cadastral"],
        BITRIX_FIELDS["matriz_filial"],
        BITRIX_FIELDS["porte_empresa"],
        BITRIX_FIELDS["estado"],
    )
}

_CNPJA_OFFICE_PAYLOAD = {
    "taxId": CNPJ_VALIDO,
    "founded": "1990-01-01",
    "head": True,
    "statusDate": "2020-01-01",
    "status": {"id": 1, "text": "Ativa"},
    "company": {"name": "Empresa Exemplo", "equity": 1000.0, "members": []},
}


def bitrix_handler():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("crm.deal.get.json"):
            return httpx.Response(200, json={"result": _DEAL_ATUAL})
        if request.url.path.endswith("crm.deal.fields.json"):
            return httpx.Response(200, json={"result": _ITEMS_LISTAS_VAZIAS})
        if request.url.path.endswith("crm.deal.update.json"):
            return httpx.Response(200, json={"result": True})
        raise AssertionError(f"chamada Bitrix inesperada: {request.url.path}")

    return handler


def cnpja_handler():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_CNPJA_OFFICE_PAYLOAD, headers={"content-type": "application/json"})

    return handler


async def test_health_nao_exige_chave_de_integracao(app_client: httpx.AsyncClient) -> None:
    resposta = await app_client.get("/health")
    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok"}


async def test_syncs_sem_historico_retorna_lista_vazia(app_client: httpx.AsyncClient) -> None:
    resposta = await app_client.get(
        f"/api/v1/cnpj/syncs/{DEAL_ID}",
        headers={"X-Integration-Key": INTEGRATION_API_KEY},
    )
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["deal_id"] == DEAL_ID
    assert corpo["history"] == []


async def test_syncs_sem_chave_retorna_401(app_client: httpx.AsyncClient) -> None:
    resposta = await app_client.get(f"/api/v1/cnpj/syncs/{DEAL_ID}")
    assert resposta.status_code == 401


async def test_syncs_reflete_execucao_anterior(app_client: httpx.AsyncClient) -> None:
    app_client._transport.app.state.bitrix_handler_box.handler = bitrix_handler()  # type: ignore[attr-defined]
    app_client._transport.app.state.cnpja_handler_box.handler = cnpja_handler()  # type: ignore[attr-defined]

    resposta_enrich = await app_client.post(
        "/api/v1/cnpj/enrich-deal",
        json={"deal_id": DEAL_ID, "force": False, "dry_run": False},
        headers={"X-Integration-Key": INTEGRATION_API_KEY},
    )
    assert resposta_enrich.status_code == 200

    resposta_syncs = await app_client.get(
        f"/api/v1/cnpj/syncs/{DEAL_ID}",
        headers={"X-Integration-Key": INTEGRATION_API_KEY},
    )
    assert resposta_syncs.status_code == 200
    historico = resposta_syncs.json()["history"]
    assert len(historico) == 1
    assert historico[0]["status"] == "success"
    assert historico[0]["cnpj"] == CNPJ_VALIDO
