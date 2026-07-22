"""Excecoes proprias da aplicacao."""


class AppError(Exception):
    """Excecao base de todas as excecoes proprias da aplicacao."""

    # construtor que guarda a mensagem legivel do erro
    def __init__(self, message: str) -> None:
        # mensagem de erro legivel
        self.message = message
        # chama o construtor da excecao base com a mensagem
        super().__init__(message)


class InvalidCnpjError(AppError):
    """CNPJ ausente, com formato invalido ou digitos verificadores incorretos."""


class BitrixApiError(AppError):
    """Erro retornado pela API do Bitrix24 (HTTP ou campo error/error_description)."""

    # construtor que tambem guarda o codigo de erro retornado pelo Bitrix, quando existir
    def __init__(self, message: str, error_code: str | None = None) -> None:
        # codigo de erro original retornado pelo Bitrix (campo "error")
        self.error_code = error_code
        # chama o construtor da classe pai com a mensagem
        super().__init__(message)


class CnpjaApiError(AppError):
    """Erro generico ao consultar a API publica da CNPJa."""


class CnpjaNotFoundError(CnpjaApiError):
    """CNPJ nao encontrado na base publica da CNPJa (HTTP 404)."""


class CnpjaRateLimitError(CnpjaApiError):
    """Limite de requisicoes da CNPJa atingido (HTTP 429)."""

    # construtor que guarda o tempo sugerido de espera, quando informado pela API
    def __init__(self, message: str, retry_after_seconds: float | None = None) -> None:
        # segundos sugeridos de espera antes de tentar novamente (header Retry-After)
        self.retry_after_seconds = retry_after_seconds
        # chama o construtor da classe pai com a mensagem
        super().__init__(message)


class ConfigurationError(AppError):
    """Configuracao ausente ou inconsistente (ex: opcao de lista esperada nao encontrada)."""


class ConcurrentSyncError(AppError):
    """Ja existe uma sincronizacao em andamento para o mesmo deal_id."""
