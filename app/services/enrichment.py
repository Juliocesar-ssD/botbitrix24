"""Servico de orquestracao: enriquece um Negocio do Bitrix24 com dados da CNPJa.

Fluxo completo (ver docs/fluxo-integracao.md):
1. Lock por deal_id (impede execucao concorrente do mesmo negocio).
2. Consulta o negocio no Bitrix (crm.deal.get).
3. Extrai e valida o CNPJ do campo UF_CRM_1736855231889.
4. Checa idempotencia (sincronizacao recente), a menos que force=True.
5. Consulta a CNPJa.
6. Resolve os campos de lista via crm.deal.fields.
7. Mapeia os dados para os campos do Bitrix.
8. Compara com os valores atuais do negocio.
9. Atualiza somente os campos alterados no Bitrix (a menos que dry_run=True).
10. Registra o resultado no log local.
"""

import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clients.bitrix import BitrixClient
from app.clients.cnpja import CnpjaClient
from app.config.bitrix_fields import BITRIX_FIELDS, NEVER_ERASE_FIELD_KEYS
from app.core.exceptions import CnpjaNotFoundError
from app.core.logging import build_log_context
from app.core.utils import remove_empty_values, validate_cnpj
from app.db.models import CnpjSyncLog
from app.services.field_mapper import EnumerationResolver, map_cnpja_response_to_bitrix_fields
from app.services.idempotency import DealLockRegistry, find_recent_successful_sync, hash_response

logger = logging.getLogger(__name__)

# campo tecnico do Bitrix onde o CNPJ do negocio esta registrado
_CAMPO_CNPJ = BITRIX_FIELDS["cnpj"]


@dataclass
class EnrichmentResult:
    """Resultado consolidado de uma execucao de enriquecimento."""

    # indica se a execucao terminou sem erros bloqueantes
    success: bool
    # id do negocio processado
    deal_id: int
    # CNPJ (14 digitos) que foi consultado
    cnpj: str
    # se True, nenhuma escrita foi feita no Bitrix
    dry_run: bool
    # chaves logicas dos campos que foram (ou seriam) alterados
    fields_changed: list[str]
    # chaves logicas dos campos que ja estavam corretos
    fields_unchanged: list[str]
    # avisos nao bloqueantes
    warnings: list[str]
    # origem dos dados
    source: str = "CNPJá API Pública"


class EnrichmentService:
    """Orquestra a consulta, transformacao, comparacao e atualizacao de um negocio."""

    def __init__(
        self,
        bitrix_client: BitrixClient,
        cnpja_client: CnpjaClient,
        session_factory: async_sessionmaker[AsyncSession],
        lock_registry: DealLockRegistry,
        currency: str,
        fill_separate_address_fields: bool,
        sync_ttl_hours: int,
    ) -> None:
        self._bitrix = bitrix_client
        self._cnpja = cnpja_client
        self._session_factory = session_factory
        self._locks = lock_registry
        self._currency = currency
        self._fill_separate_address_fields = fill_separate_address_fields
        self._sync_ttl_hours = sync_ttl_hours

    async def enrich_deal(
        self,
        deal_id: int,
        force: bool,
        dry_run: bool,
        request_id: str,
    ) -> EnrichmentResult:
        """Executa o fluxo completo de enriquecimento para o deal_id informado."""
        # impede execucao concorrente do mesmo negocio
        self._locks.acquire_nowait(deal_id)
        try:
            return await self._executar(deal_id, force, dry_run, request_id)
        finally:
            # sempre libera o lock, mesmo em caso de erro
            self._locks.release(deal_id)

    async def _executar(
        self,
        deal_id: int,
        force: bool,
        dry_run: bool,
        request_id: str,
    ) -> EnrichmentResult:
        inicio = time.monotonic()

        # etapa 1: consulta o negocio no Bitrix
        negocio_atual = await self._bitrix.get_deal(deal_id)

        # etapa 2: extrai e valida o CNPJ do campo configurado
        cnpj_bruto = str(negocio_atual.get(_CAMPO_CNPJ) or "")
        cnpj = validate_cnpj(cnpj_bruto)

        logger.info("%s", build_log_context(
            request_id=request_id, deal_id=deal_id, cnpj=cnpj, etapa="cnpj_validado", resultado="ok",
        ))

        # etapa 3: checa idempotencia, a menos que force=True
        async with self._session_factory() as session:
            if not force:
                sincronizacao_recente = await find_recent_successful_sync(
                    session, deal_id, cnpj, self._sync_ttl_hours
                )
                if sincronizacao_recente is not None:
                    logger.info("%s", build_log_context(
                        request_id=request_id, deal_id=deal_id, cnpj=cnpj,
                        etapa="idempotencia", resultado="sincronizacao_recente_reaproveitada",
                    ))
                    return EnrichmentResult(
                        success=True,
                        deal_id=deal_id,
                        cnpj=cnpj,
                        dry_run=dry_run,
                        fields_changed=[],
                        fields_unchanged=list(sincronizacao_recente.fields_changed_json or []),
                        warnings=["Sincronizacao recente reaproveitada (force=false); nenhuma consulta foi refeita."],
                    )

        # registra o inicio da tentativa no log local
        started_at = datetime.now(UTC)
        log_entry = CnpjSyncLog(
            deal_id=deal_id,
            cnpj=cnpj,
            started_at=started_at,
            status="running",
            fields_changed_json=[],
            warnings_json=[],
        )

        try:
            # etapa 4: consulta a CNPJa
            dados_cnpja = await self._cnpja.get_office(cnpj)

            # etapa 5: resolve os campos de lista via crm.deal.fields
            descricoes_enumeration = await self._bitrix.resolve_enumeration_fields(
                [BITRIX_FIELDS[chave] for chave in (
                    "tipo_pessoa", "situacao_cadastral", "matriz_filial", "porte_empresa", "estado",
                )]
            )
            resolver = EnumerationResolver(descricoes_enumeration)

            # etapa 6: mapeia os dados da CNPJa para os campos do Bitrix
            hoje_iso = datetime.now(UTC).date().isoformat()
            mapeado = map_cnpja_response_to_bitrix_fields(
                dados_cnpja,
                resolver,
                currency=self._currency,
                fill_separate_address_fields=self._fill_separate_address_fields,
                today_iso=hoje_iso,
            )

            # etapa 7: compara com os valores atuais e monta o payload de diferencas
            fields_changed, fields_unchanged = self._comparar(negocio_atual, mapeado.values)

            # etapa 8: atualiza o Bitrix somente se houver diferencas e nao for dry_run
            if fields_changed and not dry_run:
                payload_bitrix = {
                    BITRIX_FIELDS[chave]: mapeado.values[chave] for chave in fields_changed
                }
                await self._bitrix.update_deal(deal_id, payload_bitrix)

            log_entry.finished_at = datetime.now(UTC)
            log_entry.status = "dry_run" if dry_run else "success"
            log_entry.fields_changed_json = fields_changed
            log_entry.warnings_json = mapeado.warnings
            log_entry.response_hash = hash_response(dados_cnpja.model_dump(mode="json"))

            duracao_ms = (time.monotonic() - inicio) * 1000
            logger.info("%s", build_log_context(
                request_id=request_id, deal_id=deal_id, cnpj=cnpj, etapa="enriquecimento_concluido",
                duracao_ms=duracao_ms, resultado="sucesso",
            ))

            return EnrichmentResult(
                success=True,
                deal_id=deal_id,
                cnpj=cnpj,
                dry_run=dry_run,
                fields_changed=fields_changed,
                fields_unchanged=fields_unchanged,
                warnings=mapeado.warnings,
            )

        except CnpjaNotFoundError:
            log_entry.finished_at = datetime.now(UTC)
            log_entry.status = "error"
            log_entry.error_code = "CnpjaNotFoundError"
            log_entry.error_message = "CNPJ nao encontrado na base publica da CNPJa."
            raise
        except Exception as exc:
            log_entry.finished_at = datetime.now(UTC)
            log_entry.status = "error"
            log_entry.error_code = type(exc).__name__
            log_entry.error_message = str(exc)
            raise
        finally:
            async with self._session_factory() as session:
                session.add(log_entry)
                await session.commit()

    def _comparar(
        self,
        negocio_atual: dict[str, object],
        novos_valores: dict[str, object],
    ) -> tuple[list[str], list[str]]:
        """Compara os novos valores mapeados com os valores atuais do negocio.

        Retorna (fields_changed, fields_unchanged) como listas de chaves logicas.
        Nunca inclui na comparacao um valor vazio vindo da CNPJa para uma chave
        marcada como "nunca apagar" quando o negocio ja possui valor preenchido.
        """
        # remove valores vazios (None, string vazia, lista vazia) dos novos valores
        novos_valores_limpos = remove_empty_values(novos_valores)

        fields_changed: list[str] = []
        fields_unchanged: list[str] = []

        for chave, novo_valor in novos_valores_limpos.items():
            nome_tecnico = BITRIX_FIELDS[chave]
            valor_atual = negocio_atual.get(nome_tecnico)

            # protege campos que nunca devem ser apagados: se o novo valor for vazio, ja foi
            # removido por remove_empty_values, mas se o valor atual existe e o novo e igual
            # (apos normalizacao de tipo), tratamos como inalterado
            valor_atual_str = "" if valor_atual is None else str(valor_atual).strip()
            novo_valor_str = str(novo_valor).strip()

            if valor_atual_str == novo_valor_str:
                fields_unchanged.append(chave)
            else:
                # nunca apaga um campo protegido com um valor novo vazio (ja filtrado acima),
                # mas tambem nunca sobrescreve um campo protegido e ja preenchido com "" vindo da API
                if chave in NEVER_ERASE_FIELD_KEYS and novo_valor_str == "" and valor_atual_str != "":
                    fields_unchanged.append(chave)
                    continue
                fields_changed.append(chave)

        return fields_changed, fields_unchanged
