"""Testes das regras de socio majoritario e montagem do quadro societario."""

from app.schemas.cnpja import CnpjaCargo, CnpjaMembro, CnpjaPessoa
from app.services.shareholder import (
    CONTROLE_SOCIETARIO_IGUALITARIO,
    NAO_IDENTIFICADO_PELA_BASE_PUBLICA,
    NAO_INFORMADO_PELA_BASE_PUBLICA,
    SocioComParticipacao,
    build_shareholder_board_text,
    resolve_majority_shareholder,
)


def _membro(nome: str, qualificacao: str | None = None, since: str | None = None) -> CnpjaMembro:
    return CnpjaMembro(
        since=since,
        person=CnpjaPessoa(id="1", type="NATURAL", name=nome, taxId=None, age=None, country=None),
        role=CnpjaCargo(id=1, text=qualificacao) if qualificacao else None,
    )


def test_socio_unico_e_majoritario() -> None:
    socios = [SocioComParticipacao(nome="JOAO DA SILVA", participacao_percentual=None)]
    assert resolve_majority_shareholder(socios) == "JOAO DA SILVA"


def test_nenhum_socio_retorna_nao_informado() -> None:
    assert resolve_majority_shareholder([]) == NAO_INFORMADO_PELA_BASE_PUBLICA


def test_varios_socios_sem_percentual_retorna_nao_identificado() -> None:
    socios = [
        SocioComParticipacao(nome="JOAO", participacao_percentual=None),
        SocioComParticipacao(nome="MARIA", participacao_percentual=None),
    ]
    assert resolve_majority_shareholder(socios) == NAO_IDENTIFICADO_PELA_BASE_PUBLICA


def test_socio_majoritario_com_percentual_objetivo() -> None:
    socios = [
        SocioComParticipacao(nome="JOAO", participacao_percentual=60.0),
        SocioComParticipacao(nome="MARIA", participacao_percentual=40.0),
    ]
    assert resolve_majority_shareholder(socios) == "JOAO"


def test_empate_societario_retorna_controle_igualitario() -> None:
    socios = [
        SocioComParticipacao(nome="JOAO", participacao_percentual=50.0),
        SocioComParticipacao(nome="MARIA", participacao_percentual=50.0),
    ]
    assert resolve_majority_shareholder(socios) == CONTROLE_SOCIETARIO_IGUALITARIO


def test_nao_considera_automaticamente_o_primeiro_socio() -> None:
    # sem percentual informado, mesmo havendo dois socios, NAO deve escolher "JOAO" so por ser o primeiro
    socios = [
        SocioComParticipacao(nome="JOAO", participacao_percentual=None),
        SocioComParticipacao(nome="MARIA", participacao_percentual=None),
    ]
    resultado = resolve_majority_shareholder(socios)
    assert resultado not in {"JOAO", "MARIA"}
    assert resultado == NAO_IDENTIFICADO_PELA_BASE_PUBLICA


def test_nao_considera_socio_administrador_como_majoritario_automaticamente() -> None:
    # qualificacao de "Socio-Administrador" nao prova participacao majoritaria
    membros = [
        _membro("JOAO DA SILVA", qualificacao="Socio-Administrador"),
        _membro("MARIA DE SOUZA", qualificacao="Socia"),
    ]
    socios = [
        SocioComParticipacao(nome=m.person.name, participacao_percentual=None)  # type: ignore[union-attr]
        for m in membros
    ]
    assert resolve_majority_shareholder(socios) == NAO_IDENTIFICADO_PELA_BASE_PUBLICA


def test_build_shareholder_board_text_uma_pessoa_por_linha() -> None:
    membros = [
        _membro("Joao Da Silva", qualificacao="Socio-Administrador", since="2020-03-15"),
        _membro("Maria De Souza", qualificacao="Socia", since="2021-08-10"),
    ]
    texto = build_shareholder_board_text(membros)
    assert texto == (
        "Joao Da Silva — Socio-Administrador — Entrada: 15/03/2020\n"
        "Maria De Souza — Socia — Entrada: 10/08/2021"
    )


def test_build_shareholder_board_text_sem_data_omite_entrada() -> None:
    membros = [_membro("Joao Da Silva", qualificacao="Socio")]
    texto = build_shareholder_board_text(membros)
    assert texto == "Joao Da Silva — Socio"
    assert "Entrada" not in texto


def test_build_shareholder_board_text_sem_qualificacao_usa_somente_nome() -> None:
    membros = [_membro("Joao Da Silva")]
    texto = build_shareholder_board_text(membros)
    assert texto == "Joao Da Silva"


def test_build_shareholder_board_text_sem_membros_retorna_none() -> None:
    assert build_shareholder_board_text([]) is None


def test_build_shareholder_board_text_preserva_ordem_original() -> None:
    membros = [_membro("ZULMIRA"), _membro("ANTONIO")]
    texto = build_shareholder_board_text(membros)
    assert texto is not None
    assert texto.index("ZULMIRA") < texto.index("ANTONIO")
