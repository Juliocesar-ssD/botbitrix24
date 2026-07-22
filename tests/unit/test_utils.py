"""Testes de limpeza/validacao de CNPJ e funcoes utilitarias puras."""

import pytest

from app.core.exceptions import InvalidCnpjError
from app.core.utils import (
    clean_document,
    format_bitrix_money,
    is_valid_cnpj,
    normalize_text,
    remove_empty_values,
    validate_cnpj,
)

CNPJ_VALIDO_BANCO_DO_BRASIL = "00000000000191"
CNPJ_VALIDO_FORMATADO = "00.000.000/0001-91"


def test_clean_document_remove_pontuacao() -> None:
    assert clean_document("12.345.678/0001-95") == "12345678000195"


def test_clean_document_remove_espacos() -> None:
    assert clean_document(" 12 345 678 0001 95 ") == "12345678000195"


def test_clean_document_valor_vazio() -> None:
    assert clean_document("") == ""


def test_is_valid_cnpj_valido() -> None:
    assert is_valid_cnpj(CNPJ_VALIDO_BANCO_DO_BRASIL) is True


def test_is_valid_cnpj_digitos_verificadores_incorretos() -> None:
    assert is_valid_cnpj("00000000000199") is False


def test_is_valid_cnpj_tamanho_incorreto() -> None:
    assert is_valid_cnpj("123") is False


def test_is_valid_cnpj_sequencia_repetida() -> None:
    assert is_valid_cnpj("11111111111111") is False


def test_validate_cnpj_com_formatacao() -> None:
    assert validate_cnpj(CNPJ_VALIDO_FORMATADO) == CNPJ_VALIDO_BANCO_DO_BRASIL


def test_validate_cnpj_ausente_levanta_erro() -> None:
    with pytest.raises(InvalidCnpjError):
        validate_cnpj("")


def test_validate_cnpj_tamanho_invalido_levanta_erro() -> None:
    with pytest.raises(InvalidCnpjError):
        validate_cnpj("123456789")


def test_validate_cnpj_digitos_invalidos_levanta_erro() -> None:
    with pytest.raises(InvalidCnpjError):
        validate_cnpj("00000000000199")


def test_validate_cnpj_cpf_11_digitos_levanta_erro() -> None:
    with pytest.raises(InvalidCnpjError):
        validate_cnpj("11144477735")


def test_normalize_text_remove_acentos_e_maiuscula() -> None:
    assert normalize_text("São Paulo") == "SAO PAULO"


def test_normalize_text_colapsa_espacos() -> None:
    assert normalize_text("  Rio   de   Janeiro  ") == "RIO DE JANEIRO"


def test_remove_empty_values_remove_none_string_vazia_e_lista_vazia() -> None:
    entrada = {"a": None, "b": "", "c": [], "d": "valor", "e": 0, "f": False}
    resultado = remove_empty_values(entrada)
    assert resultado == {"d": "valor", "e": 0, "f": False}


def test_format_bitrix_money_formato_tecnico() -> None:
    assert format_bitrix_money(100000.0, "BRL") == "100000.00|BRL"


def test_format_bitrix_money_duas_casas_decimais() -> None:
    assert format_bitrix_money(1234.5, "BRL") == "1234.50|BRL"


def test_format_bitrix_money_zero() -> None:
    assert format_bitrix_money(0, "BRL") == "0.00|BRL"


def test_format_bitrix_money_valor_inteiro() -> None:
    assert format_bitrix_money(2500, "BRL") == "2500.00|BRL"


def test_format_bitrix_money_valor_ja_com_duas_casas() -> None:
    # formato confirmado no portal real via crm.deal.update no campo Capital Social
    assert format_bitrix_money(98765.43, "BRL") == "98765.43|BRL"


def test_format_bitrix_money_arredonda_terceira_casa_decimal() -> None:
    assert format_bitrix_money(123456.789, "BRL") == "123456.79|BRL"


def test_format_bitrix_money_nao_contem_simbolo_de_moeda() -> None:
    resultado = format_bitrix_money(98765.43, "BRL")
    assert "R$" not in resultado


def test_format_bitrix_money_nao_contem_separador_de_milhar() -> None:
    resultado = format_bitrix_money(123456.789, "BRL")
    assert "," not in resultado


def test_format_bitrix_money_usa_moeda_informada() -> None:
    assert format_bitrix_money(10.5, "USD") == "10.50|USD"
