"""Testes de integracao do endpoint POST /api/v1/cnpj/enrich-deal, com Bitrix e CNPJa mockados."""

import asyncio
import json
from datetime import UTC, datetime

import httpx
import pytest

from app.config.bitrix_fields import BITRIX_FIELDS
from tests.integration.conftest import INTEGRATION_API_KEY

CNPJ_VALIDO = "00000000000191"
CNPJ_FORMATADO = "00.000.000/0001-91"
DEAL_ID = 61229

_DEAL_ATUAL = {
    "ID": str(DEAL_ID),
    BITRIX_FIELDS["cnpj"]: CNPJ_FORMATADO,
    BITRIX_FIELDS["razao_social"]: "Razao Social Antiga LTDA",
}

_ITEMS_LISTAS_COMPLETAS = {
    BITRIX_FIELDS["tipo_pessoa"]: [
        {"ID": "351", "VALUE": "PESSOA FISICA"},
        {"ID": "353", "VALUE": "PESSOA JURIDICA"},
    ],
    BITRIX_FIELDS["situacao_cadastral"]: [
        {"ID": "355", "VALUE": "ATIVA"},
        {"ID": "365", "VALUE": "NAO INFORMADA"},
    ],
    BITRIX_FIELDS["matriz_filial"]: [
        {"ID": "367", "VALUE": "MATRIZ"},
        {"ID": "369", "VALUE": "FILIAL"},
    ],
    BITRIX_FIELDS["porte_empresa"]: [
        {"ID": "373", "VALUE": "MICROEMPRESA"},
        {"ID": "377", "VALUE": "DEMAIS"},
    ],
    BITRIX_FIELDS["estado"]: [
        {"ID": "45", "VALUE": "RIO DE JANEIRO"},
    ],
}

_CNPJA_OFFICE_PAYLOAD = {
    "taxId": CNPJ_VALIDO,
    "alias": "Nome Fantasia Novo",
    "founded": "1990-01-01",
    "head": True,
    "statusDate": "2020-01-01",
    "status": {"id": 1, "text": "Ativa"},
    "address": {
        "street": "Avenida Rio Branco",
        "number": "156",
        "district": "Centro",
        "city": "Rio de Janeiro",
        "state": "RJ",
        "zip": "20040009",
        "country": {"id": 76, "name": "Brasil"},
    },
    "mainActivity": {"id": 6911701, "text": "Servicos advocaticios"},
    "company": {
        "name": "Empresa Exemplo Atualizada LTDA",
        "equity": 100000.0,
        "nature": {"id": 2062, "text": "Sociedade Empresaria Limitada"},
        "size": {"id": 1, "acronym": "DEMAIS", "text": "Demais"},
        "members": [
            {
                "since": "2020-03-15",
                "person": {"id": "1", "type": "NATURAL", "name": "Joao Da Silva"},
                "role": {"id": 1, "text": "Socio-Administrador"},
            }
        ],
    },
}


def _bitrix_handler_padrao(deal: dict[str, object] | None = None):
    """Handler Bitrix que responde crm.deal.get, crm.deal.fields e crm.deal.update com sucesso."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("crm.deal.get.json"):
            return httpx.Response(200, json={"result": deal or _DEAL_ATUAL})
        if request.url.path.endswith("crm.deal.fields.json"):
            campos = {
                nome_tecnico: {"type": "enumeration", "title": nome_tecnico, "items": items}
                for nome_tecnico, items in _ITEMS_LISTAS_COMPLETAS.items()
            }
            return httpx.Response(200, json={"result": campos})
        if request.url.path.endswith("crm.deal.update.json"):
            return httpx.Response(200, json={"result": True})
        raise AssertionError(f"chamada Bitrix inesperada: {request.url.path}")

    return handler


def _cnpja_handler_padrao(payload: dict[str, object] | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json=payload or _CNPJA_OFFICE_PAYLOAD, headers={"content-type": "application/json"}
        )

    return handler


@pytest.fixture
def bitrix_handler():
    return _bitrix_handler_padrao()


@pytest.fixture
def cnpja_handler():
    return _cnpja_handler_padrao()


def _set_bitrix_handler(app_client: httpx.AsyncClient, handler) -> None:
    app_client._transport.app.state.bitrix_handler_box.handler = handler  # type: ignore[attr-defined]


def _set_cnpja_handler(app_client: httpx.AsyncClient, handler) -> None:
    app_client._transport.app.state.cnpja_handler_box.handler = handler  # type: ignore[attr-defined]


async def test_enrich_deal_sucesso_retorna_campos_alterados(app_client: httpx.AsyncClient) -> None:
    resposta = await app_client.post(
        "/api/v1/cnpj/enrich-deal",
        json={"deal_id": DEAL_ID, "force": False, "dry_run": False},
        headers={"X-Integration-Key": INTEGRATION_API_KEY},
    )
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["success"] is True
    assert corpo["deal_id"] == DEAL_ID
    assert corpo["cnpj"] == CNPJ_VALIDO
    assert corpo["dry_run"] is False
    assert "razao_social" in corpo["fields_changed"]
    assert corpo["source"] == "CNPJá API Pública"


async def test_enrich_deal_envia_email_corporativo_no_update(app_client: httpx.AsyncClient) -> None:
    payload_com_email = dict(_CNPJA_OFFICE_PAYLOAD)
    payload_com_email["emails"] = [
        {"ownership": "PERSONAL", "address": "pessoal@gmail.com", "domain": "gmail.com"},
        {"ownership": "CORPORATE", "address": "Marcus.Martins@UVA.BR", "domain": "uva.br"},
    ]

    payload_enviado_ao_bitrix: dict[str, object] = {}

    def bitrix_captura_update(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("crm.deal.update.json"):
            dados = json.loads(request.content)
            payload_enviado_ao_bitrix.update(dados.get("fields", {}))
            return httpx.Response(200, json={"result": True})
        return _bitrix_handler_padrao()(request)

    _set_bitrix_handler(app_client, bitrix_captura_update)
    _set_cnpja_handler(app_client, _cnpja_handler_padrao(payload_com_email))

    resposta = await app_client.post(
        "/api/v1/cnpj/enrich-deal",
        json={"deal_id": DEAL_ID, "force": False, "dry_run": False},
        headers={"X-Integration-Key": INTEGRATION_API_KEY},
    )
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert "email" in corpo["fields_changed"]
    assert payload_enviado_ao_bitrix[BITRIX_FIELDS["email"]] == "marcus.martins@uva.br"


async def test_enrich_deal_envia_telefones_no_update_quando_campo_vazio(app_client: httpx.AsyncClient) -> None:
    payload_com_telefones = dict(_CNPJA_OFFICE_PAYLOAD)
    payload_com_telefones["phones"] = [
        {"type": "LANDLINE", "area": "21", "number": "25748900"},
        {"type": "MOBILE", "area": "21", "number": "999999999"},
    ]

    payload_enviado_ao_bitrix: dict[str, object] = {}

    def bitrix_captura_update(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("crm.deal.update.json"):
            dados = json.loads(request.content)
            payload_enviado_ao_bitrix.update(dados.get("fields", {}))
            return httpx.Response(200, json={"result": True})
        return _bitrix_handler_padrao()(request)  # deal atual sem telefones (campo vazio)

    _set_bitrix_handler(app_client, bitrix_captura_update)
    _set_cnpja_handler(app_client, _cnpja_handler_padrao(payload_com_telefones))

    resposta = await app_client.post(
        "/api/v1/cnpj/enrich-deal",
        json={"deal_id": DEAL_ID, "force": False, "dry_run": False},
        headers={"X-Integration-Key": INTEGRATION_API_KEY},
    )
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert "telefones_localizados" in corpo["fields_changed"]
    assert payload_enviado_ao_bitrix[BITRIX_FIELDS["telefones_localizados"]] == (
        "1. (21) 2574-8900 — TELEFONE FIXO\n2. (21) 99999-9999 — CELULAR"
    )


async def test_enrich_deal_preserva_telefones_preenchidos_manualmente_com_force_false(
    app_client: httpx.AsyncClient,
) -> None:
    # a CNPJa nao retorna telefones desta vez; o campo ja preenchido manualmente deve ser preservado
    payload_sem_telefones = dict(_CNPJA_OFFICE_PAYLOAD)
    payload_sem_telefones["phones"] = []

    deal_com_telefone_manual = dict(_DEAL_ATUAL)
    deal_com_telefone_manual[BITRIX_FIELDS["telefones_localizados"]] = "1. (11) 3333-4444 — TELEFONE FIXO"

    def bitrix_sem_update_de_telefone(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("crm.deal.update.json"):
            dados = json.loads(request.content)
            assert BITRIX_FIELDS["telefones_localizados"] not in dados.get("fields", {})
            return httpx.Response(200, json={"result": True})
        return _bitrix_handler_padrao(deal_com_telefone_manual)(request)

    _set_bitrix_handler(app_client, bitrix_sem_update_de_telefone)
    _set_cnpja_handler(app_client, _cnpja_handler_padrao(payload_sem_telefones))

    resposta = await app_client.post(
        "/api/v1/cnpj/enrich-deal",
        json={"deal_id": DEAL_ID, "force": False, "dry_run": False},
        headers={"X-Integration-Key": INTEGRATION_API_KEY},
    )
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert "telefones_localizados" not in corpo["fields_changed"]
    assert "cnpja_phones_not_available" in corpo["warnings"]


async def test_enrich_deal_force_true_substitui_telefones_pelo_retorno_mais_recente(
    app_client: httpx.AsyncClient,
) -> None:
    deal_com_telefone_antigo = dict(_DEAL_ATUAL)
    deal_com_telefone_antigo[BITRIX_FIELDS["telefones_localizados"]] = "1. (11) 3333-4444 — TELEFONE FIXO"

    payload_com_telefone_novo = dict(_CNPJA_OFFICE_PAYLOAD)
    payload_com_telefone_novo["phones"] = [{"type": "MOBILE", "area": "21", "number": "988887777"}]

    payload_enviado_ao_bitrix: dict[str, object] = {}

    def bitrix_captura_update(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("crm.deal.update.json"):
            dados = json.loads(request.content)
            payload_enviado_ao_bitrix.update(dados.get("fields", {}))
            return httpx.Response(200, json={"result": True})
        return _bitrix_handler_padrao(deal_com_telefone_antigo)(request)

    _set_bitrix_handler(app_client, bitrix_captura_update)
    _set_cnpja_handler(app_client, _cnpja_handler_padrao(payload_com_telefone_novo))

    resposta = await app_client.post(
        "/api/v1/cnpj/enrich-deal",
        json={"deal_id": DEAL_ID, "force": True, "dry_run": False},
        headers={"X-Integration-Key": INTEGRATION_API_KEY},
    )
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert "telefones_localizados" in corpo["fields_changed"]
    assert payload_enviado_ao_bitrix[BITRIX_FIELDS["telefones_localizados"]] == "1. (21) 98888-7777 — CELULAR"


async def test_enrich_deal_dry_run_nao_atualiza_mas_reporta_diferencas(app_client: httpx.AsyncClient) -> None:
    def bitrix_sem_update(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("crm.deal.update.json"):
            raise AssertionError("dry_run=True nao deveria chamar crm.deal.update")
        return _bitrix_handler_padrao()(request)

    _set_bitrix_handler(app_client, bitrix_sem_update)

    resposta = await app_client.post(
        "/api/v1/cnpj/enrich-deal",
        json={"deal_id": DEAL_ID, "force": False, "dry_run": True},
        headers={"X-Integration-Key": INTEGRATION_API_KEY},
    )
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["dry_run"] is True
    assert "razao_social" in corpo["fields_changed"]


async def test_enrich_deal_sem_alteracoes_nao_chama_update(app_client: httpx.AsyncClient) -> None:
    deal_ja_atualizado = dict(_DEAL_ATUAL)
    deal_ja_atualizado[BITRIX_FIELDS["razao_social"]] = "Empresa Exemplo Atualizada LTDA"
    deal_ja_atualizado[BITRIX_FIELDS["nome_fantasia"]] = "Nome Fantasia Novo"
    deal_ja_atualizado[BITRIX_FIELDS["tipo_pessoa"]] = "353"
    deal_ja_atualizado[BITRIX_FIELDS["situacao_cadastral"]] = "355"
    deal_ja_atualizado[BITRIX_FIELDS["data_situacao_cadastral"]] = "2020-01-01"
    deal_ja_atualizado[BITRIX_FIELDS["matriz_filial"]] = "367"
    deal_ja_atualizado[BITRIX_FIELDS["porte_empresa"]] = "377"
    deal_ja_atualizado[BITRIX_FIELDS["natureza_juridica"]] = "2062 — Sociedade Empresaria Limitada"
    deal_ja_atualizado[BITRIX_FIELDS["capital_social"]] = "100000.00|BRL"
    deal_ja_atualizado[BITRIX_FIELDS["cnae_principal"]] = "6911701 — Servicos advocaticios"
    deal_ja_atualizado[BITRIX_FIELDS["data_abertura"]] = "1990-01-01"
    deal_ja_atualizado[BITRIX_FIELDS["data_ultima_consulta"]] = datetime.now(UTC).date().isoformat()
    deal_ja_atualizado[BITRIX_FIELDS["cep"]] = "20040009"
    deal_ja_atualizado[BITRIX_FIELDS["logradouro"]] = "Avenida Rio Branco"
    deal_ja_atualizado[BITRIX_FIELDS["numero_endereco"]] = "156"
    deal_ja_atualizado[BITRIX_FIELDS["bairro"]] = "Centro"
    deal_ja_atualizado[BITRIX_FIELDS["municipio"]] = "Rio de Janeiro"
    deal_ja_atualizado[BITRIX_FIELDS["estado"]] = "45"
    deal_ja_atualizado[BITRIX_FIELDS["endereco_completo"]] = (
        "Avenida Rio Branco, 156, Centro, Rio de Janeiro, RJ, CEP 20040-009, Brasil"
    )
    deal_ja_atualizado[BITRIX_FIELDS["quadro_societario"]] = (
        "Joao Da Silva — Socio-Administrador — Entrada: 15/03/2020"
    )
    deal_ja_atualizado[BITRIX_FIELDS["socio_majoritario"]] = "Joao Da Silva"

    def bitrix_sem_update(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("crm.deal.update.json"):
            raise AssertionError("nao deveria chamar update quando nao ha diferencas")
        return _bitrix_handler_padrao(deal_ja_atualizado)(request)

    _set_bitrix_handler(app_client, bitrix_sem_update)

    resposta = await app_client.post(
        "/api/v1/cnpj/enrich-deal",
        json={"deal_id": DEAL_ID, "force": False, "dry_run": False},
        headers={"X-Integration-Key": INTEGRATION_API_KEY},
    )
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["fields_changed"] == []
    assert "razao_social" in corpo["fields_unchanged"]


async def test_enrich_deal_cnpj_invalido_retorna_400(app_client: httpx.AsyncClient) -> None:
    deal_com_cnpj_invalido = dict(_DEAL_ATUAL)
    deal_com_cnpj_invalido[BITRIX_FIELDS["cnpj"]] = "123"
    _set_bitrix_handler(app_client, _bitrix_handler_padrao(deal_com_cnpj_invalido))

    resposta = await app_client.post(
        "/api/v1/cnpj/enrich-deal",
        json={"deal_id": DEAL_ID, "force": False, "dry_run": False},
        headers={"X-Integration-Key": INTEGRATION_API_KEY},
    )
    assert resposta.status_code == 400


async def test_enrich_deal_sem_chave_retorna_401(app_client: httpx.AsyncClient) -> None:
    resposta = await app_client.post(
        "/api/v1/cnpj/enrich-deal",
        json={"deal_id": DEAL_ID, "force": False, "dry_run": False},
    )
    assert resposta.status_code == 401


async def test_enrich_deal_chave_invalida_retorna_401(app_client: httpx.AsyncClient) -> None:
    resposta = await app_client.post(
        "/api/v1/cnpj/enrich-deal",
        json={"deal_id": DEAL_ID, "force": False, "dry_run": False},
        headers={"X-Integration-Key": "chave-errada"},
    )
    assert resposta.status_code == 401


async def test_enrich_deal_cnpj_nao_encontrado_na_cnpja_retorna_404(app_client: httpx.AsyncClient) -> None:
    def cnpja_404(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "not found"})

    _set_cnpja_handler(app_client, cnpja_404)

    resposta = await app_client.post(
        "/api/v1/cnpj/enrich-deal",
        json={"deal_id": DEAL_ID, "force": False, "dry_run": False},
        headers={"X-Integration-Key": INTEGRATION_API_KEY},
    )
    assert resposta.status_code == 404


async def test_enrich_deal_rate_limit_cnpja_retorna_429(app_client: httpx.AsyncClient) -> None:
    def cnpja_429(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"message": "rate limited"}, headers={"retry-after": "0.01"})

    _set_cnpja_handler(app_client, cnpja_429)

    resposta = await app_client.post(
        "/api/v1/cnpj/enrich-deal",
        json={"deal_id": DEAL_ID, "force": False, "dry_run": False},
        headers={"X-Integration-Key": INTEGRATION_API_KEY},
    )
    assert resposta.status_code == 429


async def test_enrich_deal_erro_bitrix_retorna_502(app_client: httpx.AsyncClient) -> None:
    def bitrix_com_erro(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("crm.deal.get.json"):
            return httpx.Response(200, json={"error": "INVALID_REQUEST", "error_description": "Negocio nao existe"})
        raise AssertionError("nao deveria chamar outros metodos apos falha no get")

    _set_bitrix_handler(app_client, bitrix_com_erro)

    resposta = await app_client.post(
        "/api/v1/cnpj/enrich-deal",
        json={"deal_id": DEAL_ID, "force": False, "dry_run": False},
        headers={"X-Integration-Key": INTEGRATION_API_KEY},
    )
    assert resposta.status_code == 502


async def test_enrich_deal_force_true_ignora_sincronizacao_recente(app_client: httpx.AsyncClient) -> None:
    chamadas_cnpja = 0

    def cnpja_contador(request: httpx.Request) -> httpx.Response:
        nonlocal chamadas_cnpja
        chamadas_cnpja += 1
        return httpx.Response(200, json=_CNPJA_OFFICE_PAYLOAD, headers={"content-type": "application/json"})

    _set_cnpja_handler(app_client, cnpja_contador)

    primeira = await app_client.post(
        "/api/v1/cnpj/enrich-deal",
        json={"deal_id": DEAL_ID, "force": False, "dry_run": False},
        headers={"X-Integration-Key": INTEGRATION_API_KEY},
    )
    assert primeira.status_code == 200
    assert chamadas_cnpja == 1

    segunda_sem_force = await app_client.post(
        "/api/v1/cnpj/enrich-deal",
        json={"deal_id": DEAL_ID, "force": False, "dry_run": False},
        headers={"X-Integration-Key": INTEGRATION_API_KEY},
    )
    assert segunda_sem_force.status_code == 200
    # sem force, a sincronizacao recente e reaproveitada: nao deve consultar a CNPJa de novo
    assert chamadas_cnpja == 1

    terceira_com_force = await app_client.post(
        "/api/v1/cnpj/enrich-deal",
        json={"deal_id": DEAL_ID, "force": True, "dry_run": False},
        headers={"X-Integration-Key": INTEGRATION_API_KEY},
    )
    assert terceira_com_force.status_code == 200
    # com force=True, a CNPJa deve ser consultada novamente
    assert chamadas_cnpja == 2


async def test_enrich_deal_sincronizacao_concorrente_retorna_409(app_client: httpx.AsyncClient) -> None:
    liberar_bitrix = asyncio.Event()

    def bitrix_que_responde_normalmente(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("crm.deal.get.json"):
            return httpx.Response(200, json={"result": _DEAL_ATUAL})
        if request.url.path.endswith("crm.deal.fields.json"):
            campos = {
                nome_tecnico: {"type": "enumeration", "title": nome_tecnico, "items": items}
                for nome_tecnico, items in _ITEMS_LISTAS_COMPLETAS.items()
            }
            return httpx.Response(200, json={"result": campos})
        if request.url.path.endswith("crm.deal.update.json"):
            return httpx.Response(200, json={"result": True})
        raise AssertionError("chamada inesperada durante o teste de concorrencia")

    _set_bitrix_handler(app_client, bitrix_que_responde_normalmente)

    async def chamada_lenta_cnpja(request: httpx.Request) -> httpx.Response:
        # e a etapa mais lenta do fluxo real; segurando-a aqui garante que a segunda
        # requisicao encontre o lock do deal_id ainda ocupado pela primeira.
        await liberar_bitrix.wait()
        return httpx.Response(200, json=_CNPJA_OFFICE_PAYLOAD, headers={"content-type": "application/json"})

    _set_cnpja_handler(app_client, chamada_lenta_cnpja)

    tarefa_1 = asyncio.create_task(
        app_client.post(
            "/api/v1/cnpj/enrich-deal",
            json={"deal_id": DEAL_ID, "force": False, "dry_run": False},
            headers={"X-Integration-Key": INTEGRATION_API_KEY},
        )
    )
    await asyncio.sleep(0.05)

    resposta_2 = await app_client.post(
        "/api/v1/cnpj/enrich-deal",
        json={"deal_id": DEAL_ID, "force": False, "dry_run": False},
        headers={"X-Integration-Key": INTEGRATION_API_KEY},
    )
    assert resposta_2.status_code == 409

    liberar_bitrix.set()
    resposta_1 = await tarefa_1
    assert resposta_1.status_code == 200
