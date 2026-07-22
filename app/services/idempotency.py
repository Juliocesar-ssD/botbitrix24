"""Controle de idempotencia: lock por deal_id e verificacao de sincronizacao recente."""

import hashlib
import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConcurrentSyncError
from app.db.models import CnpjSyncLog


class DealLockRegistry:
    """Mantem o conjunto de deal_id com sincronizacao em andamento.

    Nao usa asyncio.Lock (que serve para *esperar* a vaga liberar); aqui a regra
    de negocio e rejeitar imediatamente uma segunda sincronizacao simultanea do
    mesmo negocio (HTTP 409), entao um `set` simples e suficiente e mais direto.
    O event loop unico do asyncio garante que nao ha corrida entre a checagem
    e a insercao dentro de `acquire_nowait` (nenhum `await` ocorre entre elas).
    """

    def __init__(self) -> None:
        # conjunto de deal_id atualmente com sincronizacao em andamento
        self._em_andamento: set[int] = set()

    def acquire_nowait(self, deal_id: int) -> None:
        """Marca o deal_id como em sincronizacao, levantando erro se ja estiver em uso."""
        if deal_id in self._em_andamento:
            raise ConcurrentSyncError(f"Ja existe uma sincronizacao em andamento para o deal_id={deal_id}.")
        self._em_andamento.add(deal_id)

    def release(self, deal_id: int) -> None:
        """Libera o deal_id, permitindo uma nova sincronizacao."""
        self._em_andamento.discard(deal_id)


def hash_response(payload: dict[str, object]) -> str:
    """Gera um hash estavel (sha256) de um dicionario, para detectar respostas identicas da CNPJa."""
    # serializa com chaves ordenadas para garantir hash estavel independente da ordem original
    serializado = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(serializado.encode("utf-8")).hexdigest()


async def find_recent_successful_sync(
    session: AsyncSession,
    deal_id: int,
    cnpj: str,
    ttl_hours: int,
) -> CnpjSyncLog | None:
    """Busca uma sincronizacao bem-sucedida recente (dentro do TTL) para o mesmo deal_id + CNPJ."""
    # limite de tempo: qualquer sincronizacao mais recente que este instante conta como "recente"
    limite = datetime.now(UTC) - timedelta(hours=ttl_hours)
    # busca o registro de sucesso mais recente para a combinacao deal_id + CNPJ
    consulta = (
        select(CnpjSyncLog)
        .where(
            CnpjSyncLog.deal_id == deal_id,
            CnpjSyncLog.cnpj == cnpj,
            CnpjSyncLog.status == "success",
            CnpjSyncLog.finished_at.is_not(None),
            CnpjSyncLog.finished_at >= limite.replace(tzinfo=None),
        )
        .order_by(CnpjSyncLog.finished_at.desc())
        .limit(1)
    )
    resultado = await session.execute(consulta)
    return resultado.scalar_one_or_none()
