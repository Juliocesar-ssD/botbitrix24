"""Rota de compatibilidade para o Webhook de saida do Bitrix24.

O Bitrix24 (webhook de saida / automacao) chama esta rota via POST com
parametros de query, no formato:

    POST /webhook/bitrix/enriquecer-cnpj?token=...&dealId=61229&force=true&dryRun=false

Esta rota nao duplica nenhuma logica de negocio: apenas traduz os parametros
de query para o mesmo EnrichmentService usado por POST /api/v1/cnpj/enrich-deal
(ver app/api/routes/cnpj.py), reaproveitando a mesma dependencia
`get_enrichment_service` e o mesmo tratamento de excecoes.
"""

import logging
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import get_request_id
from app.api.routes.cnpj import get_enrichment_service
from app.config.settings import Settings, get_settings
from app.core.exceptions import (
    BitrixApiError,
    CnpjaApiError,
    CnpjaNotFoundError,
    CnpjaRateLimitError,
    ConcurrentSyncError,
    ConfigurationError,
    InvalidCnpjError,
)
from app.schemas.responses import EnrichDealResponse
from app.services.enrichment import EnrichmentService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook/bitrix", tags=["webhook"])


def _require_valid_token(token: str, settings: Settings) -> None:
    """Valida o token de query em tempo constante; nunca registra o valor recebido."""
    if not token or not secrets.compare_digest(token, settings.integration_api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalido ou ausente.",
        )


@router.post("/enriquecer-cnpj", response_model=EnrichDealResponse)
async def enriquecer_cnpj_via_webhook(
    service: Annotated[EnrichmentService, Depends(get_enrichment_service)],
    request_id: Annotated[str, Depends(get_request_id)],
    settings: Annotated[Settings, Depends(get_settings)],
    token: Annotated[str, Query(description="Token de integracao (equivalente a X-Integration-Key).")],
    dealId: Annotated[int, Query(gt=0, description="ID do negocio (deal) no Bitrix24.")],
    force: Annotated[bool, Query(description="Ignora sincronizacao recente e consulta novamente.")] = False,
    dryRun: Annotated[bool, Query(description="Consulta e compara, mas nao atualiza o Bitrix.")] = False,
) -> EnrichDealResponse:
    """Compatibilidade com o Webhook de saida do Bitrix24 (POST com parametros de query)."""
    _require_valid_token(token, settings)

    try:
        resultado = await service.enrich_deal(
            deal_id=dealId,
            force=force,
            dry_run=dryRun,
            request_id=request_id,
        )
    except InvalidCnpjError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message) from exc
    except ConcurrentSyncError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.message) from exc
    except CnpjaRateLimitError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=exc.message) from exc
    except CnpjaNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.message) from exc
    except ConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=exc.message) from exc
    except (BitrixApiError, CnpjaApiError) as exc:
        logger.warning("Erro de integracao externa ao processar dealId=%s: %s", dealId, exc.message)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=exc.message) from exc

    return EnrichDealResponse(
        success=resultado.success,
        deal_id=resultado.deal_id,
        cnpj=resultado.cnpj,
        dry_run=resultado.dry_run,
        fields_changed=resultado.fields_changed,
        fields_unchanged=resultado.fields_unchanged,
        warnings=resultado.warnings,
        source=resultado.source,
    )
