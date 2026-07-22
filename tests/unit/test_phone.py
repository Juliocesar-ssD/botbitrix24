"""Testes da formatacao dos telefones (campo Telefones Localizados, UF_CRM_1784751137)."""

from app.schemas.cnpja import CnpjaPhone
from app.services.phone import build_phones_text


def test_telefone_fixo_formata_com_ddd() -> None:
    phones = [CnpjaPhone(type="LANDLINE", area="21", number="25748900")]
    texto = build_phones_text(phones)
    assert texto == "1. (21) 2574-8900 — TELEFONE FIXO"


def test_celular_formata_com_ddd() -> None:
    phones = [CnpjaPhone(type="MOBILE", area="21", number="999999999")]
    texto = build_phones_text(phones)
    assert texto == "1. (21) 99999-9999 — CELULAR"


def test_varios_telefones_um_por_linha_numerados() -> None:
    phones = [
        CnpjaPhone(type="LANDLINE", area="21", number="25748900"),
        CnpjaPhone(type="MOBILE", area="21", number="999999999"),
    ]
    texto = build_phones_text(phones)
    assert texto == (
        "1. (21) 2574-8900 — TELEFONE FIXO\n"
        "2. (21) 99999-9999 — CELULAR"
    )


def test_telefones_duplicados_sao_removidos_comparando_ddd_e_numero() -> None:
    phones = [
        CnpjaPhone(type="LANDLINE", area="21", number="25748900"),
        CnpjaPhone(type="LANDLINE", area="21", number="2574-8900"),  # mesmo numero, com formatacao
        CnpjaPhone(type="MOBILE", area="21", number="999999999"),
    ]
    texto = build_phones_text(phones)
    assert texto == (
        "1. (21) 2574-8900 — TELEFONE FIXO\n"
        "2. (21) 99999-9999 — CELULAR"
    )


def test_telefone_sem_ddd_formata_sem_parenteses() -> None:
    phones = [CnpjaPhone(type="LANDLINE", area=None, number="25748900")]
    texto = build_phones_text(phones)
    assert texto == "1. 2574-8900 — TELEFONE FIXO"


def test_item_sem_numero_e_ignorado() -> None:
    phones = [
        CnpjaPhone(type="MOBILE", area="21", number=None),
        CnpjaPhone(type="LANDLINE", area="21", number="25748900"),
    ]
    texto = build_phones_text(phones)
    assert texto == "1. (21) 2574-8900 — TELEFONE FIXO"


def test_lista_vazia_retorna_none() -> None:
    assert build_phones_text([]) is None


def test_numero_8_digitos() -> None:
    phones = [CnpjaPhone(type=None, area="11", number="25748900")]
    texto = build_phones_text(phones)
    assert "2574-8900" in texto  # type: ignore[operator]


def test_numero_9_digitos() -> None:
    phones = [CnpjaPhone(type=None, area="11", number="912345678")]
    texto = build_phones_text(phones)
    assert "91234-5678" in texto  # type: ignore[operator]


def test_tipo_desconhecido_traduz_para_telefone() -> None:
    phones = [CnpjaPhone(type="FAX", area="21", number="25748900")]
    texto = build_phones_text(phones)
    assert texto == "1. (21) 2574-8900 — TELEFONE"


def test_tipo_ausente_traduz_para_telefone() -> None:
    phones = [CnpjaPhone(type=None, area="21", number="25748900")]
    texto = build_phones_text(phones)
    assert texto == "1. (21) 2574-8900 — TELEFONE"


def test_area_e_number_mantem_somente_digitos() -> None:
    phones = [CnpjaPhone(type="MOBILE", area="(21)", number="99999-9999")]
    texto = build_phones_text(phones)
    assert texto == "1. (21) 99999-9999 — CELULAR"


def test_nao_menciona_whatsapp() -> None:
    phones = [CnpjaPhone(type="MOBILE", area="21", number="999999999")]
    texto = build_phones_text(phones)
    assert "whatsapp" not in texto.lower()  # type: ignore[union-attr]
