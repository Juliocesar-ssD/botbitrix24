"""Cliente isolado para a API REST do Bitrix24 (metodos crm.deal.*).

Toda chamada REST ao Bitrix passa por este modulo. Isso permite trocar
crm.deal.get/update por crm.item.get/update no futuro sem alterar o
restante do sistema (ver docs/referencias-externas.md).
"""

import asyncio
import logging
from typing import Any

import httpx

from app.core.exceptions import BitrixApiError
from app.core.security import mask_webhook_url
from app.schemas.bitrix import BitrixApiResponse, BitrixFieldDescription

# logger deste modulo
logger = logging.getLogger(__name__)

# numero maximo de tentativas em erros transitorios (timeout, 5xx)
_MAX_TENTATIVAS = 3

# fator base (segundos) do backoff exponencial entre tentativas
_BACKOFF_BASE_SEGUNDOS = 1.0


class BitrixClient:
    """Cliente para os metodos crm.deal.* do Bitrix24, via webhook de entrada."""

    def __init__(self, webhook_base_url: str, http_client: httpx.AsyncClient) -> None:
        # base do webhook, sem o nome do metodo (ex: https://portal.../rest/1/token)
        self._webhook_base_url = webhook_base_url.rstrip("/")
        # cliente HTTP assincrono compartilhado (injetado para permitir testes com MockTransport)
        self._http_client = http_client

    async def get_deal(self, deal_id: int) -> dict[str, Any]:
        """Consulta um negocio pelo metodo crm.deal.get.json."""
        # chama o metodo crm.deal.get com o id do negocio
        resposta = await self._chamar_metodo("crm.deal.get.json", {"id": deal_id})
        # o resultado de crm.deal.get e um objeto com os campos do negocio
        return dict(resposta.result or {})

    async def get_deal_fields(self) -> dict[str, BitrixFieldDescription]:
        """Consulta a descricao de todos os campos do Negocio via crm.deal.fields.json."""
        # chama o metodo crm.deal.fields, sem parametros
        resposta = await self._chamar_metodo("crm.deal.fields.json", {})
        # o resultado e um dicionario {nome_do_campo: descricao_do_campo}
        campos_brutos = dict(resposta.result or {})
        # converte cada descricao bruta para o modelo tipado BitrixFieldDescription
        return {
            nome: BitrixFieldDescription.model_validate(descricao)
            for nome, descricao in campos_brutos.items()
        }

    async def update_deal(self, deal_id: int, fields: dict[str, Any]) -> bool:
        """Atualiza um negocio pelo metodo crm.deal.update.json, enviando apenas os campos informados."""
        # se nao ha campos para enviar, nao faz sentido chamar o Bitrix
        if not fields:
            return True
        # chama o metodo crm.deal.update com o id do negocio e os campos alterados
        resposta = await self._chamar_metodo(
            "crm.deal.update.json",
            {"id": deal_id, "fields": fields},
        )
        # o Bitrix retorna result=true quando a atualizacao e bem-sucedida
        return bool(resposta.result)

    async def resolve_enumeration_fields(
        self, field_names: list[str]
    ) -> dict[str, BitrixFieldDescription]:
        """Retorna somente as descricoes dos campos informados que sao do tipo enumeration."""
        # busca a descricao de todos os campos do Negocio
        todos_os_campos = await self.get_deal_fields()
        # filtra apenas os campos solicitados que existem e sao do tipo "enumeration"
        return {
            nome: descricao
            for nome, descricao in todos_os_campos.items()
            if nome in field_names and descricao.type == "enumeration"
        }

    async def test_connection(self) -> bool:
        """Testa a conectividade com o webhook, chamando um metodo leve e somente leitura."""
        try:
            # crm.deal.fields e um metodo leve e nao destrutivo, adequado para health-check
            await self._chamar_metodo("crm.deal.fields.json", {})
            return True
        except BitrixApiError:
            return False

    async def _chamar_metodo(self, metodo: str, payload: dict[str, Any]) -> BitrixApiResponse:
        """Executa uma chamada POST ao metodo informado, com retries e tratamento de erros."""
        # monta a URL final do metodo REST
        url = f"{self._webhook_base_url}/{metodo}"
        # URL mascarada, usada apenas para logs (nunca loga o webhook completo)
        url_mascarada = mask_webhook_url(url)
        # controla quantas tentativas ja foram feitas
        tentativa = 0
        while True:
            tentativa += 1
            try:
                # executa a chamada HTTP POST com o payload em JSON
                resposta = await self._http_client.post(url, json=payload)
            except httpx.TimeoutException as exc:
                if tentativa >= _MAX_TENTATIVAS:
                    raise BitrixApiError(
                        f"Timeout ao chamar {metodo} apos {tentativa} tentativas."
                    ) from exc
                logger.warning("Timeout ao chamar %s (tentativa %s) em %s", metodo, tentativa, url_mascarada)
                await self._aguardar_backoff(tentativa)
                continue
            except httpx.HTTPError as exc:
                if tentativa >= _MAX_TENTATIVAS:
                    raise BitrixApiError(f"Erro de conexao ao chamar {metodo}: {exc}") from exc
                logger.warning("Erro de conexao ao chamar %s (tentativa %s) em %s", metodo, tentativa, url_mascarada)
                await self._aguardar_backoff(tentativa)
                continue

            # 5xx do lado do Bitrix e transitorio - pode tentar novamente
            if resposta.status_code >= 500:
                if tentativa >= _MAX_TENTATIVAS:
                    raise BitrixApiError(f"Erro no servidor do Bitrix ao chamar {metodo} (HTTP {resposta.status_code}).")
                logger.warning("HTTP %s ao chamar %s (tentativa %s)", resposta.status_code, metodo, tentativa)
                await self._aguardar_backoff(tentativa)
                continue

            try:
                # decodifica o corpo da resposta como JSON
                dados = resposta.json()
            except ValueError as exc:
                raise BitrixApiError(f"Resposta de {metodo} nao e um JSON valido (HTTP {resposta.status_code}).") from exc

            # converte o JSON bruto para o envelope tipado de resposta do Bitrix
            resposta_tipada = BitrixApiResponse.model_validate(dados)

            # NUNCA considera HTTP 200 como sucesso sem checar o campo "error" do corpo
            if resposta_tipada.is_error:
                # erros de validacao (parametros invalidos) nao devem ser repetidos automaticamente
                logger.warning(
                    "Bitrix retornou erro para %s: %s", metodo, resposta_tipada.error
                )
                raise BitrixApiError(
                    resposta_tipada.error_description or "Erro nao especificado retornado pelo Bitrix24.",
                    error_code=resposta_tipada.error,
                )

            # log de sucesso sem expor o webhook nem o payload completo
            logger.info("Chamada a %s concluida com sucesso.", metodo)
            return resposta_tipada

    @staticmethod
    async def _aguardar_backoff(tentativa: int) -> None:
        """Aguarda um tempo de backoff exponencial antes da proxima tentativa."""
        # backoff exponencial simples: base * 2^(tentativa - 1)
        espera = _BACKOFF_BASE_SEGUNDOS * (2 ** (tentativa - 1))
        await asyncio.sleep(espera)
