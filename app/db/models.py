"""Modelo ORM da tabela de log e idempotencia das sincronizacoes CNPJa -> Bitrix24."""

from datetime import datetime

from sqlalchemy import JSON, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CnpjSyncLog(Base):
    """Registro de uma execucao (tentativa) de sincronizacao para um deal_id + CNPJ."""

    # nome da tabela no SQLite
    __tablename__ = "cnpj_sync_log"

    # chave primaria autoincremental
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # id do negocio no Bitrix24
    deal_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    # CNPJ (14 digitos, sem mascara) consultado nesta execucao
    cnpj: Mapped[str] = mapped_column(String(14), index=True, nullable=False)
    # momento (UTC) em que a sincronizacao comecou
    started_at: Mapped[datetime] = mapped_column(nullable=False)
    # momento (UTC) em que a sincronizacao terminou; None enquanto em andamento
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    # status final: "success", "error", "skipped" ou "dry_run"
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    # codigo HTTP relevante da chamada externa (Bitrix ou CNPJa), quando aplicavel
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # lista (serializada em JSON) das chaves logicas de campos alterados
    fields_changed_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    # lista (serializada em JSON) de avisos nao bloqueantes gerados na execucao
    warnings_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    # hash da resposta normalizada da CNPJa, usado para detectar respostas identicas
    response_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # codigo da excecao propria levantada, quando houve erro
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # mensagem de erro, quando houve erro
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
