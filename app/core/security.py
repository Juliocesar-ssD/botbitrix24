"""Funcoes de seguranca: validacao do header de integracao e mascaramento de segredos."""

import hmac
import re

# padrao usado para localizar o token no final de uma URL de webhook do Bitrix24
_WEBHOOK_TOKEN_PATTERN = re.compile(r"(/rest/\d+/)([^/]+)(/?.*)$")


def constant_time_compare(value_a: str, value_b: str) -> bool:
    """Compara duas strings em tempo constante, evitando ataques de timing."""
    # usa compare_digest, que compara em tempo constante independente do conteudo
    return hmac.compare_digest(value_a.encode("utf-8"), value_b.encode("utf-8"))


def mask_webhook_url(url: str) -> str:
    """Mascara o token do webhook do Bitrix presente em uma URL, mantendo o restante legivel."""
    # tenta casar o padrao /rest/USUARIO/TOKEN no final da URL
    match = _WEBHOOK_TOKEN_PATTERN.search(url)
    # se nao casar, mascara a URL inteira por seguranca
    if not match:
        return "***"
    # prefixo antes do token (ex: https://portal.bitrix24.com.br/rest/123/)
    prefix = match.group(1)
    # sufixo depois do token (ex: /crm.deal.get.json), se existir
    suffix = match.group(3)
    # parte da URL antes do prefixo do token
    base = url[: match.start(1)]
    # remonta a URL trocando o token por asteriscos
    return f"{base}{prefix}***{suffix}"


def mask_secret(value: str, visible_chars: int = 0) -> str:
    """Mascara um segredo generico, opcionalmente mantendo alguns caracteres finais visiveis."""
    # segredo vazio ou None e mascarado por completo
    if not value:
        return "***"
    # se visible_chars for zero, mascara o segredo inteiro
    if visible_chars <= 0:
        return "***"
    # mantem apenas os ultimos N caracteres visiveis, mascarando o restante
    return f"***{value[-visible_chars:]}"


def mask_cnpj(cnpj: str) -> str:
    """Mascara um CNPJ ja limpo (14 digitos) no formato 12.***.***/****-34."""
    # se o CNPJ nao tiver 14 digitos, mascara por completo
    if len(cnpj) != 14 or not cnpj.isdigit():
        return "***"
    # dois primeiros digitos, visiveis
    inicio = cnpj[:2]
    # dois ultimos digitos, visiveis (digitos verificadores)
    fim = cnpj[-2:]
    # monta a mascara no formato solicitado
    return f"{inicio}.***.***/****-{fim}"
