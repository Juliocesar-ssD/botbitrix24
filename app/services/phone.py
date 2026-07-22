"""Formatacao dos telefones retornados pela CNPJa para o campo Telefones Localizados do Bitrix.

Regras de negocio (ver especificacao do campo UF_CRM_1784751137):
- manter somente digitos em area/number;
- ignorar registros sem numero;
- remover duplicados comparando DDD + numero;
- formatar conforme a quantidade de digitos do numero e presenca de DDD;
- traduzir o tipo (LANDLINE/MOBILE/outro) para um rotulo em portugues;
- nao informar confirmacao de WhatsApp, pois a CNPJa nao fornece esse dado.
"""

import re

from app.schemas.cnpja import CnpjaPhone

# traducao dos tipos de telefone retornados pela CNPJa para o rotulo exibido no Bitrix
_TIPO_TELEFONE_LABELS: dict[str, str] = {
    "LANDLINE": "TELEFONE FIXO",
    "MOBILE": "CELULAR",
}

# rotulo usado quando o tipo retornado pela CNPJa nao e reconhecido
_TIPO_TELEFONE_PADRAO = "TELEFONE"


def _somente_digitos(valor: str | None) -> str:
    """Remove qualquer caractere que nao seja digito."""
    return re.sub(r"\D", "", valor or "")


def _formatar_numero(area: str, number: str) -> str:
    """Formata DDD + numero conforme a quantidade de digitos do numero.

    - numero com 9 digitos (celular): (DDD) 9XXXX-XXXX
    - numero com 8 digitos (fixo): (DDD) XXXX-XXXX
    - sem DDD: XXXX-XXXX (sem parenteses)
    """
    if len(number) == 9:
        numero_formatado = f"{number[:5]}-{number[5:]}"
    elif len(number) == 8:
        numero_formatado = f"{number[:4]}-{number[4:]}"
    else:
        # quantidade de digitos fora do esperado: nao arrisca separar incorretamente
        numero_formatado = number

    if area:
        return f"({area}) {numero_formatado}"
    return numero_formatado


def _traduzir_tipo(tipo: str | None) -> str:
    """Traduz o tipo de telefone da CNPJa para o rotulo exibido no Bitrix."""
    if not tipo:
        return _TIPO_TELEFONE_PADRAO
    return _TIPO_TELEFONE_LABELS.get(tipo.strip().upper(), _TIPO_TELEFONE_PADRAO)


def build_phones_text(phones: list[CnpjaPhone]) -> str | None:
    """Monta o texto final do campo Telefones Localizados, um telefone por linha.

    Formato de cada linha: "N. (DDD) NUMERO-FORMATADO — ROTULO_DO_TIPO"
    Duplicados (mesmo DDD + numero, apos manter somente digitos) sao removidos,
    preservando a primeira ocorrencia. Registros sem numero sao ignorados.
    Retorna None se nao houver nenhum telefone valido (o chamador decide o
    warning e a preservacao do valor atual, pois a API publica pode
    simplesmente nao ter telefones para o CNPJ consultado).
    """
    vistos: set[str] = set()
    linhas: list[str] = []

    for phone in phones:
        numero_limpo = _somente_digitos(phone.number)
        # sem numero, nao ha o que exibir para este registro
        if not numero_limpo:
            continue

        area_limpa = _somente_digitos(phone.area)
        chave_duplicidade = f"{area_limpa}{numero_limpo}"
        if chave_duplicidade in vistos:
            continue
        vistos.add(chave_duplicidade)

        numero_formatado = _formatar_numero(area_limpa, numero_limpo)
        rotulo_tipo = _traduzir_tipo(phone.type)
        linhas.append(f"{len(linhas) + 1}. {numero_formatado} — {rotulo_tipo}")

    if not linhas:
        return None

    return "\n".join(linhas)
