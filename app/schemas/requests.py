"""Modelos Pydantic dos corpos de requisicao recebidos pela API interna."""

from pydantic import BaseModel, Field


class EnrichDealRequest(BaseModel):
    """Corpo esperado por POST /api/v1/cnpj/enrich-deal."""

    # id do negocio no Bitrix24 a ser enriquecido
    deal_id: int = Field(..., gt=0, description="ID do negocio (deal) no Bitrix24.")
    # se True, ignora o cache de sincronizacao recente e consulta novamente
    force: bool = Field(default=False, description="Ignora sincronizacao recente e consulta novamente.")
    # se True, executa toda a logica mas nao chama crm.deal.update
    dry_run: bool = Field(default=False, description="Consulta e compara, mas nao atualiza o Bitrix.")
