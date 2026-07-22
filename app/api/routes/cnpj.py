"""Rotas internas de enriquecimento de Negocios via CNPJa (protegidas por X-Integration-Key)."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.dependencies import (
    get_bitrix_client,
    get_cnpja_client,
    get_db_session,
    get_lock_registry,
    get_request_id,
    get_session_factory,
    require_integration_key,
)
from app.clients.bitrix import BitrixClient
from app.clients.cnpja import CnpjaClient
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
from app.db.models import CnpjSyncLog
from app.schemas.requests import EnrichDealRequest
from app.schemas.responses import EnrichDealResponse, SyncHistoryResponse, SyncLogEntry
from app.services.enrichment import EnrichmentService
from app.services.idempotency import DealLockRegistry

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/cnpj",
    tags=["cnpj"],
    dependencies=[Depends(require_integration_key)],
)


def get_enrichment_service(
    bitrix_client: Annotated[BitrixClient, Depends(get_bitrix_client)],
    cnpja_client: Annotated[CnpjaClient, Depends(get_cnpja_client)],
    session_factory: Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)],
    lock_registry: Annotated[DealLockRegistry, Depends(get_lock_registry)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> EnrichmentService:
    """Constroi o servico de enriquecimento para esta requisicao."""
    return EnrichmentService(
        bitrix_client=bitrix_client,
        cnpja_client=cnpja_client,
        session_factory=session_factory,
        lock_registry=lock_registry,
        currency=settings.bitrix_currency,
        fill_separate_address_fields=settings.fill_separate_address_fields,
        sync_ttl_hours=settings.sync_ttl_hours,
    )


@router.post("/enrich-deal", response_model=EnrichDealResponse)
async def enrich_deal(
    body: EnrichDealRequest,
    service: Annotated[EnrichmentService, Depends(get_enrichment_service)],
    request_id: Annotated[str, Depends(get_request_id)],
) -> EnrichDealResponse:
    """Consulta o negocio, busca o CNPJ na CNPJa e atualiza os campos alterados no Bitrix."""
    try:
        resultado = await service.enrich_deal(
            deal_id=body.deal_id,
            force=body.force,
            dry_run=body.dry_run,
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
        logger.warning("Erro de integracao externa ao processar deal_id=%s: %s", body.deal_id, exc.message)
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


@router.get("/syncs/{deal_id}", response_model=SyncHistoryResponse)
async def get_sync_history(
    deal_id: int,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SyncHistoryResponse:
    """Retorna o historico local de sincronizacoes de um deal_id, mais recente primeiro."""
    consulta = (
        select(CnpjSyncLog)
        .where(CnpjSyncLog.deal_id == deal_id)
        .order_by(CnpjSyncLog.started_at.desc())
    )
    resultado = await session.execute(consulta)
    registros = resultado.scalars().all()

    historico = [
        SyncLogEntry(
            id=registro.id,
            deal_id=registro.deal_id,
            cnpj=registro.cnpj,
            started_at=registro.started_at.isoformat(),
            finished_at=registro.finished_at.isoformat() if registro.finished_at else None,
            status=registro.status,
            http_status=registro.http_status,
            fields_changed=list(registro.fields_changed_json or []),
            warnings=list(registro.warnings_json or []),
            error_code=registro.error_code,
            error_message=registro.error_message,
        )
        for registro in registros
    ]

    return SyncHistoryResponse(deal_id=deal_id, history=historico)
