"""Testes do mapeamento CNPJa -> campos do Bitrix (listas, datas, dinheiro, CNAE, natureza, UF)."""

from app.config.bitrix_fields import BITRIX_FIELDS
from app.schemas.bitrix import BitrixFieldDescription, BitrixFieldItem
from app.schemas.cnpja import (
    CnpjaAtividade,
    CnpjaEmail,
    CnpjaEmpresa,
    CnpjaEndereco,
    CnpjaNatureza,
    CnpjaOfficeResponse,
    CnpjaPhone,
    CnpjaPorte,
    CnpjaStatus,
)
from app.services.field_mapper import (
    EnumerationResolver,
    _select_email,
    map_cnpja_response_to_bitrix_fields,
)


def _field_descriptions_dinamicas() -> dict[str, BitrixFieldDescription]:
    """Simula o retorno de crm.deal.fields com items reais das listas do portal."""

    def _enum(items: list[tuple[str, str]]) -> BitrixFieldDescription:
        return BitrixFieldDescription(
            type="enumeration",
            title="lista",
            items=[BitrixFieldItem(ID=id_, VALUE=value) for id_, value in items],
        )

    return {
        BITRIX_FIELDS["tipo_pessoa"]: _enum([("351", "PESSOA FISICA"), ("353", "PESSOA JURIDICA")]),
        BITRIX_FIELDS["situacao_cadastral"]: _enum(
            [
                ("355", "ATIVA"),
                ("357", "SUSPENSA"),
                ("359", "INAPTA"),
                ("361", "BAIXADA"),
                ("363", "NULA"),
                ("365", "NAO INFORMADA"),
            ]
        ),
        BITRIX_FIELDS["matriz_filial"]: _enum(
            [("367", "MATRIZ"), ("369", "FILIAL"), ("371", "NAO INFORMADA")]
        ),
        BITRIX_FIELDS["porte_empresa"]: _enum(
            [
                ("373", "MICROEMPRESA"),
                ("375", "EMPRESA DE PEQUENO PORTE"),
                ("377", "DEMAIS"),
                ("379", "NAO INFORMADO"),
            ]
        ),
        BITRIX_FIELDS["estado"]: _enum(
            [
                ("45", "RIO DE JANEIRO"),
                ("127", "SAO PAULO"),
                ("145", "DISTRITO FEDERAL"),
                ("83", "BRASILIA"),
            ]
        ),
    }


def _resolver() -> EnumerationResolver:
    return EnumerationResolver(_field_descriptions_dinamicas())


def _cnpja_minima(**overrides: object) -> CnpjaOfficeResponse:
    base = {
        "taxId": "00000000000191",
        "alias": "Nome Fantasia LTDA",
        "founded": "1990-01-01",
        "head": True,
        "statusDate": "2020-05-10",
        "status": CnpjaStatus(id=1, text="Ativa"),
        "address": CnpjaEndereco(state="RJ"),
        "mainActivity": CnpjaAtividade(id=6911701, text="Servicos advocaticios"),
        "company": CnpjaEmpresa(
            name="Empresa Exemplo LTDA",
            equity=100000.0,
            nature=CnpjaNatureza(id=2062, text="Sociedade Empresaria Limitada"),
            size=CnpjaPorte(id=1, acronym="DEMAIS", text="Demais"),
            members=[],
        ),
    }
    base.update(overrides)
    return CnpjaOfficeResponse.model_validate(base)


def test_situacao_ativa_resolve_id_correto() -> None:
    resultado = map_cnpja_response_to_bitrix_fields(
        _cnpja_minima(), _resolver(), currency="BRL", fill_separate_address_fields=True, today_iso="2026-07-21"
    )
    assert resultado.values["situacao_cadastral"] == 355


def test_situacao_desconhecida_cai_em_nao_informada() -> None:
    dados = _cnpja_minima(status=CnpjaStatus(id=99, text="Situacao Nunca Vista"))
    resultado = map_cnpja_response_to_bitrix_fields(
        dados, _resolver(), currency="BRL", fill_separate_address_fields=True, today_iso="2026-07-21"
    )
    assert resultado.values["situacao_cadastral"] == 365


def test_porte_me_normaliza_para_microempresa() -> None:
    dados = _cnpja_minima(
        company=CnpjaEmpresa(name="Empresa", size=CnpjaPorte(id=1, acronym="ME", text="Micro Empresa"))
    )
    resultado = map_cnpja_response_to_bitrix_fields(
        dados, _resolver(), currency="BRL", fill_separate_address_fields=True, today_iso="2026-07-21"
    )
    assert resultado.values["porte_empresa"] == 373


def test_porte_epp_normaliza_para_empresa_de_pequeno_porte() -> None:
    dados = _cnpja_minima(
        company=CnpjaEmpresa(name="Empresa", size=CnpjaPorte(id=1, acronym="EPP", text="Empresa Pequeno Porte"))
    )
    resultado = map_cnpja_response_to_bitrix_fields(
        dados, _resolver(), currency="BRL", fill_separate_address_fields=True, today_iso="2026-07-21"
    )
    assert resultado.values["porte_empresa"] == 375


def test_matriz_true_resolve_matriz() -> None:
    dados = _cnpja_minima(head=True)
    resultado = map_cnpja_response_to_bitrix_fields(
        dados, _resolver(), currency="BRL", fill_separate_address_fields=True, today_iso="2026-07-21"
    )
    assert resultado.values["matriz_filial"] == 367


def test_filial_false_resolve_filial() -> None:
    dados = _cnpja_minima(head=False)
    resultado = map_cnpja_response_to_bitrix_fields(
        dados, _resolver(), currency="BRL", fill_separate_address_fields=True, today_iso="2026-07-21"
    )
    assert resultado.values["matriz_filial"] == 369


def test_cnae_principal_formato_codigo_descricao() -> None:
    dados = _cnpja_minima(mainActivity=CnpjaAtividade(id=6911701, text="Servicos advocaticios"))
    resultado = map_cnpja_response_to_bitrix_fields(
        dados, _resolver(), currency="BRL", fill_separate_address_fields=True, today_iso="2026-07-21"
    )
    assert resultado.values["cnae_principal"] == "6911701 — Servicos advocaticios"


def test_natureza_juridica_formato_codigo_descricao() -> None:
    dados = _cnpja_minima(
        company=CnpjaEmpresa(name="Empresa", nature=CnpjaNatureza(id=2062, text="Sociedade Empresaria Limitada"))
    )
    resultado = map_cnpja_response_to_bitrix_fields(
        dados, _resolver(), currency="BRL", fill_separate_address_fields=True, today_iso="2026-07-21"
    )
    assert resultado.values["natureza_juridica"] == "2062 — Sociedade Empresaria Limitada"


def test_capital_social_formatado_como_money_tecnico() -> None:
    dados = _cnpja_minima(company=CnpjaEmpresa(name="Empresa", equity=250000.5))
    resultado = map_cnpja_response_to_bitrix_fields(
        dados, _resolver(), currency="BRL", fill_separate_address_fields=True, today_iso="2026-07-21"
    )
    assert resultado.values["capital_social"] == "250000.50|BRL"


def test_data_ultima_consulta_usa_data_local_do_projeto() -> None:
    resultado = map_cnpja_response_to_bitrix_fields(
        _cnpja_minima(), _resolver(), currency="BRL", fill_separate_address_fields=True, today_iso="2026-07-21"
    )
    assert resultado.values["data_ultima_consulta"] == "2026-07-21"


def test_endereco_completo_montado_mesmo_com_campos_ausentes() -> None:
    dados = _cnpja_minima(address=CnpjaEndereco(street="Rua Sem Numero", state="RJ"))
    resultado = map_cnpja_response_to_bitrix_fields(
        dados, _resolver(), currency="BRL", fill_separate_address_fields=True, today_iso="2026-07-21"
    )
    assert resultado.values["endereco_completo"] == "Rua Sem Numero, RJ"


def test_estado_rj_resolve_para_id_45() -> None:
    dados = _cnpja_minima(address=CnpjaEndereco(state="RJ"))
    resultado = map_cnpja_response_to_bitrix_fields(
        dados, _resolver(), currency="BRL", fill_separate_address_fields=True, today_iso="2026-07-21"
    )
    assert resultado.values["estado"] == 45


def test_estado_sp_resolve_para_id_127() -> None:
    dados = _cnpja_minima(address=CnpjaEndereco(state="SP"))
    resultado = map_cnpja_response_to_bitrix_fields(
        dados, _resolver(), currency="BRL", fill_separate_address_fields=True, today_iso="2026-07-21"
    )
    assert resultado.values["estado"] == 127


def test_estado_df_resolve_para_id_145_nao_para_brasilia_83() -> None:
    dados = _cnpja_minima(address=CnpjaEndereco(state="DF"))
    resultado = map_cnpja_response_to_bitrix_fields(
        dados, _resolver(), currency="BRL", fill_separate_address_fields=True, today_iso="2026-07-21"
    )
    assert resultado.values["estado"] == 145
    assert resultado.values["estado"] != 83


def test_estado_se_nao_cadastrado_gera_warning_e_nao_atualiza() -> None:
    dados = _cnpja_minima(address=CnpjaEndereco(state="SE"))
    resultado = map_cnpja_response_to_bitrix_fields(
        dados, _resolver(), currency="BRL", fill_separate_address_fields=True, today_iso="2026-07-21"
    )
    assert "estado" not in resultado.values
    assert any("SE" in aviso for aviso in resultado.warnings)
    # os demais campos continuam sendo atualizados mesmo com o warning de UF
    assert "razao_social" in resultado.values


def test_campos_vazios_nao_aparecem_no_resultado() -> None:
    dados = _cnpja_minima(alias=None)
    resultado = map_cnpja_response_to_bitrix_fields(
        dados, _resolver(), currency="BRL", fill_separate_address_fields=True, today_iso="2026-07-21"
    )
    assert "nome_fantasia" not in resultado.values


# --- e-mail (UF_CRM_1784227881933) --------------------------------------------------------


def test_select_email_unico_corporate() -> None:
    emails = [CnpjaEmail(ownership="CORPORATE", address="marcus.martins@uva.br", domain="uva.br")]
    assert _select_email(emails) == "marcus.martins@uva.br"


def test_select_email_varios_prioriza_corporate() -> None:
    emails = [
        CnpjaEmail(ownership="PERSONAL", address="pessoal@gmail.com", domain="gmail.com"),
        CnpjaEmail(ownership="CORPORATE", address="Marcus.Martins@UVA.BR", domain="uva.br"),
    ]
    # deve escolher o CORPORATE mesmo nao sendo o primeiro da lista, e normalizar para lowercase
    assert _select_email(emails) == "marcus.martins@uva.br"


def test_select_email_lista_vazia_retorna_none() -> None:
    assert _select_email([]) is None


def test_select_email_address_ausente_retorna_none() -> None:
    emails = [CnpjaEmail(ownership="CORPORATE", address=None, domain="uva.br")]
    assert _select_email(emails) is None


def test_select_email_sem_corporate_usa_primeiro_valido() -> None:
    emails = [
        CnpjaEmail(ownership="PERSONAL", address="  contato@empresa.com  ", domain="empresa.com"),
        CnpjaEmail(ownership="PERSONAL", address="outro@empresa.com", domain="empresa.com"),
    ]
    # remove espacos e usa o primeiro valido, ja que nenhum e CORPORATE
    assert _select_email(emails) == "contato@empresa.com"


def test_select_email_ignora_endereco_invalido() -> None:
    emails = [
        CnpjaEmail(ownership="CORPORATE", address="nao-e-um-email", domain=None),
        CnpjaEmail(ownership="PERSONAL", address="valido@empresa.com", domain="empresa.com"),
    ]
    assert _select_email(emails) == "valido@empresa.com"


def test_select_email_ignora_endereco_vazio() -> None:
    emails = [CnpjaEmail(ownership="CORPORATE", address="   ", domain=None)]
    assert _select_email(emails) is None


def test_mapeamento_email_corporate_unico() -> None:
    dados = _cnpja_minima(emails=[CnpjaEmail(ownership="CORPORATE", address="marcus.martins@uva.br", domain="uva.br")])
    resultado = map_cnpja_response_to_bitrix_fields(
        dados, _resolver(), currency="BRL", fill_separate_address_fields=True, today_iso="2026-07-21"
    )
    assert resultado.values["email"] == "marcus.martins@uva.br"


def test_mapeamento_email_lista_vazia_nao_preenche_campo() -> None:
    dados = _cnpja_minima(emails=[])
    resultado = map_cnpja_response_to_bitrix_fields(
        dados, _resolver(), currency="BRL", fill_separate_address_fields=True, today_iso="2026-07-21"
    )
    assert "email" not in resultado.values


def test_mapeamento_email_usa_id_tecnico_correto() -> None:
    assert BITRIX_FIELDS["email"] == "UF_CRM_1784227881933"


# --- telefones localizados (UF_CRM_1784751137) ----------------------------------------------


def test_mapeamento_telefones_preenche_campo_quando_ha_telefones() -> None:
    dados = _cnpja_minima(
        phones=[
            CnpjaPhone(type="LANDLINE", area="21", number="25748900"),
            CnpjaPhone(type="MOBILE", area="21", number="999999999"),
        ]
    )
    resultado = map_cnpja_response_to_bitrix_fields(
        dados, _resolver(), currency="BRL", fill_separate_address_fields=True, today_iso="2026-07-21"
    )
    assert resultado.values["telefones_localizados"] == (
        "1. (21) 2574-8900 — TELEFONE FIXO\n"
        "2. (21) 99999-9999 — CELULAR"
    )
    assert "cnpja_phones_not_available" not in resultado.warnings


def test_mapeamento_telefones_lista_vazia_nao_preenche_e_gera_warning() -> None:
    dados = _cnpja_minima(phones=[])
    resultado = map_cnpja_response_to_bitrix_fields(
        dados, _resolver(), currency="BRL", fill_separate_address_fields=True, today_iso="2026-07-21"
    )
    assert "telefones_localizados" not in resultado.values
    assert "cnpja_phones_not_available" in resultado.warnings


def test_mapeamento_telefones_usa_id_tecnico_correto() -> None:
    assert BITRIX_FIELDS["telefones_localizados"] == "UF_CRM_1784751137"
