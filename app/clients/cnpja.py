"""Cliente assincrono para a API publica da CNPJa (GET /office/{cnpj})."""

import asyncio
import logging
import time
from collections import deque

import httpx

from app.core.exceptions import CnpjaApiError, CnpjaNotFoundError, CnpjaRateLimitError
from app.schemas.cnpja import CnpjaOfficeResponse

# logger deste modulo
logger = logging.getLogger(__name__)

# numero maximo de tentativas em erros transitorios (timeout, 5xx, 429)
_MAX_TENTATIVAS = 3

# fator base (segundos) do backoff exponencial entre tentativas
_BACKOFF_BASE_SEGUNDOS = 1.0


class _SlidingWindowRateLimiter:
    """Limitador de taxa por janela deslizante, para respeitar o limite local de consultas/minuto."""

    def __init__(self, max_requests_per_minute: int) -> None:
        # numero maximo de requisicoes permitidas por janela de 60 segundos
        self._max_requests = max_requests_per_minute
        # timestamps (monotonic) das requisicoes feitas dentro da janela atual
        self._timestamps: deque[float] = deque()
        # lock para proteger o estado contra acesso concorrente
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Bloqueia ate que exista uma vaga disponivel na janela de 60 segundos."""
        # protege a leitura/escrita do deque contra chamadas concorrentes
        async with self._lock:
            while True:
                # marca o instante atual (relogio monotonico, nao afetado por ajustes de hora)
                agora = time.monotonic()
                # remove da janela os timestamps com mais de 60 segundos
                while self._timestamps and agora - self._timestamps[0] >= 60:
                    self._timestamps.popleft()
                # se ainda ha vaga na janela, registra a requisicao e libera
                if len(self._timestamps) < self._max_requests:
                    self._timestamps.append(agora)
                    return
                # calcula quanto falta para a requisicao mais antiga sair da janela
                espera = 60 - (agora - self._timestamps[0])
                # aguarda o tempo necessario antes de tentar novamente
                await asyncio.sleep(max(espera, 0.05))


class CnpjaClient:
    """Cliente para a API publica da CNPJa, com rate limit local e retries controlados."""

    def __init__(
        self,
        base_url: str,
        http_client: httpx.AsyncClient,
        max_requests_per_minute: int = 5,
    ) -> None:
        # URL base da API publica da CNPJa (ex: https://open.cnpja.com)
        self._base_url = base_url.rstrip("/")
        # cliente HTTP assincrono compartilhado (injetado para permitir testes com MockTransport)
        self._http_client = http_client
        # limitador de taxa local (padrao: 5 requisicoes por minuto)
        self._rate_limiter = _SlidingWindowRateLimiter(max_requests_per_minute)

    async def get_office(self, cnpj: str) -> CnpjaOfficeResponse:
        """Consulta os dados publicos de um CNPJ no endpoint /office/{cnpj}."""
        # monta a URL final da consulta
        url = f"{self._base_url}/office/{cnpj}"
        # controla quantas tentativas ja foram feitas
        tentativa = 0
        # loop de tentativas, com backoff exponencial para erros transitorios
        while True:
            tentativa += 1
            # respeita o limite local de requisicoes por minuto antes de cada tentativa
            await self._rate_limiter.acquire()
            try:
                # executa a chamada HTTP GET
                resposta = await self._http_client.get(url)
            except httpx.TimeoutException as exc:
                # timeout e um erro transitorio: tenta novamente ate o limite de tentativas
                if tentativa >= _MAX_TENTATIVAS:
                    raise CnpjaApiError(f"Timeout ao consultar a CNPJa apos {tentativa} tentativas.") from exc
                await self._aguardar_backoff(tentativa)
                continue
            except httpx.HTTPError as exc:
                # erro de rede/conexao tambem e transitorio
                if tentativa >= _MAX_TENTATIVAS:
                    raise CnpjaApiError(f"Erro de conexao com a CNPJa: {exc}") from exc
                await self._aguardar_backoff(tentativa)
                continue

            # 404: CNPJ nao encontrado na base publica - nao deve ser repetido
            if resposta.status_code == 404:
                raise CnpjaNotFoundError("CNPJ nao encontrado na base publica da CNPJa (HTTP 404).")

            # 400: entrada invalida - nao deve ser repetido
            if resposta.status_code == 400:
                raise CnpjaApiError("Requisicao invalida para a CNPJa (HTTP 400).")

            # 429: limite de requisicoes atingido no lado da CNPJa - respeita Retry-After
            if resposta.status_code == 429:
                retry_after = self._extrair_retry_after(resposta)
                if tentativa >= _MAX_TENTATIVAS:
                    raise CnpjaRateLimitError(
                        "Limite de requisicoes da CNPJa atingido (HTTP 429).",
                        retry_after_seconds=retry_after,
                    )
                await asyncio.sleep(retry_after if retry_after is not None else _BACKOFF_BASE_SEGUNDOS * tentativa)
                continue

            # 5xx: erro do lado do servidor da CNPJa - transitorio, pode tentar novamente
            if resposta.status_code >= 500:
                if tentativa >= _MAX_TENTATIVAS:
                    raise CnpjaApiError(f"Erro no servidor da CNPJa (HTTP {resposta.status_code}).")
                await self._aguardar_backoff(tentativa)
                continue

            # qualquer outro status de erro (401, 403, etc.) nao deve ser repetido
            if resposta.status_code >= 400:
                raise CnpjaApiError(f"Erro inesperado da CNPJa (HTTP {resposta.status_code}).")

            # valida o Content-Type antes de tentar decodificar o JSON
            content_type = resposta.headers.get("content-type", "")
            if "application/json" not in content_type:
                raise CnpjaApiError(f"Content-Type inesperado da CNPJa: '{content_type}'.")

            try:
                # decodifica o corpo da resposta como JSON
                dados = resposta.json()
            except ValueError as exc:
                raise CnpjaApiError("Resposta da CNPJa nao e um JSON valido.") from exc

            # log em nivel INFO sem expor o corpo completo da resposta
            logger.info("Consulta a CNPJa concluida com sucesso (status=%s).", resposta.status_code)
            # log detalhado (com corpo) somente em DEBUG
            logger.debug("Corpo da resposta da CNPJa: %s", dados)

            # valida e converte o JSON para o modelo Pydantic, tolerando campos extras/ausentes
            return CnpjaOfficeResponse.model_validate(dados)

    @staticmethod
    def _extrair_retry_after(resposta: httpx.Response) -> float | None:
        """Le o header Retry-After (em segundos) da resposta 429, quando presente."""
        # header Retry-After, se enviado pela CNPJa
        valor = resposta.headers.get("retry-after")
        if valor is None:
            return None
        try:
            # tenta interpretar como numero de segundos
            return float(valor)
        except ValueError:
            # se nao for numerico, ignora o header e usa o backoff padrao
            return None

    @staticmethod
    async def _aguardar_backoff(tentativa: int) -> None:
        """Aguarda um tempo de backoff exponencial antes da proxima tentativa."""
        # backoff exponencial simples: base * 2^(tentativa - 1)
        espera = _BACKOFF_BASE_SEGUNDOS * (2 ** (tentativa - 1))
        await asyncio.sleep(espera)
