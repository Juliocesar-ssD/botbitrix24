"""Testes de mascaramento de segredos e comparacao segura do header de integracao."""

from app.core.security import constant_time_compare, mask_cnpj, mask_secret, mask_webhook_url


def test_mask_cnpj_formato_esperado() -> None:
    assert mask_cnpj("00000000000191") == "00.***.***/****-91"


def test_mask_cnpj_tamanho_invalido_mascara_tudo() -> None:
    assert mask_cnpj("123") == "***"


def test_mask_webhook_url_oculta_token() -> None:
    url = "https://portal.bitrix24.com.br/rest/123/segredo-super-secreto/crm.deal.get.json"
    resultado = mask_webhook_url(url)
    assert "segredo-super-secreto" not in resultado
    assert resultado == "https://portal.bitrix24.com.br/rest/123/***/crm.deal.get.json"


def test_mask_webhook_url_sem_padrao_mascara_tudo() -> None:
    assert mask_webhook_url("https://exemplo.com/qualquer-coisa") == "***"


def test_mask_secret_padrao_mascara_tudo() -> None:
    assert mask_secret("chave-secreta") == "***"


def test_mask_secret_vazio() -> None:
    assert mask_secret("") == "***"


def test_constant_time_compare_valores_iguais() -> None:
    assert constant_time_compare("chave-correta", "chave-correta") is True


def test_constant_time_compare_valores_diferentes() -> None:
    assert constant_time_compare("chave-correta", "chave-errada") is False
