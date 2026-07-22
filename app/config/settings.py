"""Configuracoes da aplicacao, carregadas de variaveis de ambiente / .env."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuracoes tipadas da aplicacao."""

    # modelo de configuracao: le do arquivo .env, ignora chaves desconhecidas
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # base do webhook do Bitrix24, sem o nome do metodo no final
    bitrix_webhook_base_url: str

    # chave exigida no header X-Integration-Key
    integration_api_key: str

    # base da API publica da CNPJa
    cnpja_base_url: str = "https://open.cnpja.com"

    # string de conexao assincrona do banco local (SQLite)
    database_url: str = "sqlite+aiosqlite:///./data/cnpj_sync.db"

    # timeout em segundos para chamadas HTTP externas
    http_timeout_seconds: float = 20.0

    # limite local de consultas por minuto a CNPJa
    max_cnpja_requests_per_minute: int = 5

    # nivel de log da aplicacao
    log_level: str = "INFO"

    # controla se os campos individuais de endereco sao preenchidos
    fill_separate_address_fields: bool = True

    # moeda usada para formatar o campo money (capital social)
    bitrix_currency: str = "BRL"

    # horas de validade de uma sincronizacao antes de permitir nova consulta sem force=true
    sync_ttl_hours: int = 24


@lru_cache
def get_settings() -> Settings:
    """Retorna uma instancia cacheada das configuracoes (evita reler o .env a cada chamada)."""
    # cria e cacheia a instancia de Settings
    return Settings()
