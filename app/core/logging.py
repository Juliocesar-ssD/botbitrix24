"""Configuracao de logging estruturado da aplicacao."""

import logging
import sys
from typing import Any

from app.core.security import mask_cnpj


def configure_logging(level: str) -> None:
    """Configura o logging raiz da aplicacao com o nivel informado."""
    # configura o logging raiz para escrever em stdout no formato definido
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
        force=True,
    )


def build_log_context(
    *,
    request_id: str,
    deal_id: int,
    cnpj: str,
    etapa: str,
    duracao_ms: float | None = None,
    resultado: str | None = None,
) -> dict[str, Any]:
    """Monta um dicionario de contexto de log com o CNPJ ja mascarado.

    Nunca inclui URL de webhook, token ou header de integracao.
    """
    contexto: dict[str, Any] = {
        # identificador da requisicao, para correlacionar linhas de log
        "request_id": request_id,
        # id do negocio no Bitrix24
        "deal_id": deal_id,
        # CNPJ mascarado (nunca o CNPJ completo em nivel INFO)
        "cnpj": mask_cnpj(cnpj),
        # etapa do fluxo de enriquecimento (ex: "consulta_cnpja", "update_bitrix")
        "etapa": etapa,
    }
    # duracao da etapa em milissegundos, quando informada
    if duracao_ms is not None:
        contexto["duracao_ms"] = round(duracao_ms, 2)
    # resultado da etapa (ex: "sucesso", "erro"), quando informado
    if resultado is not None:
        contexto["resultado"] = resultado
    return contexto
