"""Rota de health-check, sem exigencia de autenticacao."""

from fastapi import APIRouter

from app.schemas.responses import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Retorna status ok se a aplicacao esta respondendo."""
    # health-check simples, sem dependencias externas
    return HealthResponse(status="ok")
