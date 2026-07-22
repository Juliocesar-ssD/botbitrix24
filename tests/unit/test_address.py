"""Testes de montagem do endereco completo textual."""

from app.schemas.cnpja import CnpjaEndereco, CnpjaPais
from app.services.address import build_full_address


def test_endereco_completo_com_todos_os_campos() -> None:
    endereco = CnpjaEndereco(
        street="Avenida Rio Branco",
        number="156",
        district="Centro",
        city="Rio de Janeiro",
        state="RJ",
        details="Sala 802",
        zip="20040009",
        country=CnpjaPais(id=76, name="Brasil"),
    )
    resultado = build_full_address(endereco)
    assert resultado == (
        "Avenida Rio Branco, 156, Sala 802, Centro, Rio de Janeiro, RJ, CEP 20040-009, Brasil"
    )


def test_endereco_sem_complemento_nao_gera_separador_vazio() -> None:
    endereco = CnpjaEndereco(
        street="Rua A",
        number="10",
        district="Bairro X",
        city="Cidade Y",
        state="SP",
        details=None,
        zip="01000000",
        country=CnpjaPais(id=76, name="Brasil"),
    )
    resultado = build_full_address(endereco)
    assert resultado == "Rua A, 10, Bairro X, Cidade Y, SP, CEP 01000-000, Brasil"
    assert ",," not in (resultado or "")


def test_endereco_none_retorna_none() -> None:
    assert build_full_address(None) is None


def test_endereco_vazio_retorna_none() -> None:
    endereco = CnpjaEndereco()
    assert build_full_address(endereco) is None
