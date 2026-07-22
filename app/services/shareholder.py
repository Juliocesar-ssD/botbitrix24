"""Regras de quadro societario e identificacao do socio majoritario.

A resposta publica da CNPJa (GET /office/{cnpj}) NAO informa percentual de
participacao/quotas por socio (ver docs/referencias-externas.md). Por isso,
na pratica, os cenarios 2 e 3 da regra de negocio (participacao objetiva e
empate) dependem de uma fonte que informe participacao - o codigo abaixo
esta preparado para isso via campo opcional `participacao_percentual`,
mas com a API publica atual o caminho real e sempre o cenario 4
("varios socios sem participacao informada").
"""

from dataclasses import dataclass

from app.core.utils import normalize_text
from app.schemas.cnpja import CnpjaMembro

# texto retornado quando ha exatamente um socio empatado na maior participacao
CONTROLE_SOCIETARIO_IGUALITARIO = "CONTROLE SOCIETARIO IGUALITARIO"

# texto retornado quando ha mais de um socio e nenhuma participacao objetiva foi informada
NAO_IDENTIFICADO_PELA_BASE_PUBLICA = "NAO IDENTIFICADO PELA BASE PUBLICA"

# texto retornado quando nenhum socio foi retornado pela API
NAO_INFORMADO_PELA_BASE_PUBLICA = "NAO INFORMADO PELA BASE PUBLICA"


@dataclass(frozen=True)
class SocioComParticipacao:
    """Representa um socio e sua participacao percentual, quando conhecida."""

    # nome do socio
    nome: str
    # participacao percentual (0-100), ou None se nao informada pela fonte
    participacao_percentual: float | None


def resolve_majority_shareholder(
    socios: list[SocioComParticipacao],
) -> str:
    """Aplica as regras de negocio para determinar o texto do socio majoritario.

    Regras (nesta ordem):
    1. Nenhum socio -> NAO_INFORMADO_PELA_BASE_PUBLICA.
    2. Um unico socio -> nome desse socio.
    3. Varios socios, todos sem participacao informada -> NAO_IDENTIFICADO_PELA_BASE_PUBLICA.
    4. Varios socios com participacao informada -> nome do maior; empate -> CONTROLE_SOCIETARIO_IGUALITARIO.

    Nunca considera automaticamente o primeiro item, o socio-administrador,
    o mais antigo ou o representante legal como majoritario.
    """
    # cenario 5: nenhum socio retornado pela API
    if not socios:
        return NAO_INFORMADO_PELA_BASE_PUBLICA

    # cenario 1: exatamente um socio - ele e o majoritario por definicao
    if len(socios) == 1:
        return socios[0].nome

    # filtra apenas os socios que tem participacao percentual objetiva informada
    socios_com_percentual = [s for s in socios if s.participacao_percentual is not None]

    # cenario 4: mais de um socio e nenhum com participacao informada
    if not socios_com_percentual:
        return NAO_IDENTIFICADO_PELA_BASE_PUBLICA

    # identifica a maior participacao percentual entre os socios informados
    maior_participacao = max(s.participacao_percentual for s in socios_com_percentual)  # type: ignore[type-var]
    # lista todos os socios que empatam na maior participacao
    socios_no_topo = [s for s in socios_com_percentual if s.participacao_percentual == maior_participacao]

    # cenario 3: empate entre dois ou mais socios na maior participacao
    if len(socios_no_topo) > 1:
        return CONTROLE_SOCIETARIO_IGUALITARIO

    # cenario 2: um unico socio com a maior participacao
    return socios_no_topo[0].nome


def build_shareholder_board_text(membros: list[CnpjaMembro]) -> str | None:
    """Monta o texto legivel do quadro societario, uma pessoa por linha.

    Formato por linha: "NOME — QUALIFICACAO — Entrada: DD/MM/AAAA"
    Omite a qualificacao quando ausente e a parte "Entrada" quando a data nao existir.
    Preserva a ordem original retornada pela API.
    """
    linhas: list[str] = []
    # percorre os membros na ordem original da API (nao reordena)
    for membro in membros:
        # sem dados de pessoa, nao ha o que exibir para este membro
        if membro.person is None or not membro.person.name:
            continue
        # nome normalizado (espacos colapsados), sem alterar capitalizacao original
        nome = " ".join(membro.person.name.split())

        # monta a linha comecando pelo nome
        partes_linha = [nome]

        # inclui a qualificacao somente se informada
        if membro.role is not None and membro.role.text:
            partes_linha.append(membro.role.text.strip())

        # inclui a data de entrada somente se informada, convertida para DD/MM/AAAA
        data_entrada = _formatar_data_entrada(membro.since)
        if data_entrada is not None:
            partes_linha.append(f"Entrada: {data_entrada}")

        # junta as partes da linha com o separador " — "
        linhas.append(" — ".join(partes_linha))

    # se nenhum membro valido foi encontrado, nao ha texto para montar
    if not linhas:
        return None

    # uma linha por integrante do quadro societario
    return "\n".join(linhas)


def _formatar_data_entrada(data_iso: str | None) -> str | None:
    """Converte uma data ISO 'YYYY-MM-DD' para 'DD/MM/AAAA'; retorna None se ausente/invalida."""
    # sem data informada, omite a parte "Entrada"
    if not data_iso:
        return None
    # espera exatamente o formato ISO "YYYY-MM-DD" (10 caracteres)
    partes = data_iso.split("-")
    if len(partes) != 3:
        return None
    ano, mes, dia = partes
    # remonta no formato brasileiro DD/MM/AAAA
    return f"{dia}/{mes}/{ano}"


def is_participacao_igualitaria(texto: str) -> bool:
    """Util para testes: verifica se o texto corresponde ao caso de empate societario."""
    # compara de forma normalizada para tolerar variacoes de acentuacao/caixa
    return normalize_text(texto) == normalize_text(CONTROLE_SOCIETARIO_IGUALITARIO)
