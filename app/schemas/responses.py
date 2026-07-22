"""Modelos Pydantic das respostas devolvidas pela API interna."""

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Resposta de GET /health."""

    # status fixo indicando que a aplicacao esta operacional
    status: str = "ok"


class EnrichDealResponse(BaseModel):
    """Resposta de POST /api/v1/cnpj/enrich-deal."""

    # indica se a execucao terminou sem erros bloqueantes
    success: bool
    # id do negocio processado
    deal_id: int
    # CNPJ (14 digitos, sem mascara) que foi consultado
    cnpj: str
    # se True, nenhuma escrita foi feita no Bitrix
    dry_run: bool
    # chaves logicas dos campos que foram (ou seriam, em dry_run) alterados
    fields_changed: list[str] = Field(default_factory=list)
    # chaves logicas dos campos que ja estavam com o valor correto
    fields_unchanged: list[str] = Field(default_factory=list)
    # avisos nao bloqueantes (ex: UF nao cadastrada, quadro societario ausente)
    warnings: list[str] = Field(default_factory=list)
    # origem dos dados usados no enriquecimento
    source: str = "CNPJá API Pública"


class SyncLogEntry(BaseModel):
    """Um registro do historico local de sincronizacoes de um deal_id."""

    # identificador interno do registro
    id: int
    # id do negocio no Bitrix24
    deal_id: int
    # CNPJ consultado nesta execucao
    cnpj: str
    # momento em que a sincronizacao comecou (ISO 8601)
    started_at: str
    # momento em que a sincronizacao terminou (ISO 8601), None se ainda em andamento
    finished_at: str | None
    # status final da sincronizacao (ex: "success", "error", "skipped")
    status: str
    # codigo HTTP da chamada relevante (Bitrix ou CNPJa), quando aplicavel
    http_status: int | None
    # chaves logicas dos campos alterados nesta execucao
    fields_changed: list[str]
    # avisos nao bloqueantes gerados nesta execucao
    warnings: list[str]
    # codigo da excecao propria levantada, quando houve erro
    error_code: str | None
    # mensagem de erro, quando houve erro
    error_message: str | None


class SyncHistoryResponse(BaseModel):
    """Resposta de GET /api/v1/cnpj/syncs/{deal_id}."""

    # id do negocio consultado
    deal_id: int
    # historico de sincronizacoes, mais recente primeiro
    history: list[SyncLogEntry]
