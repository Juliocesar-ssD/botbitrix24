"""Criacao do engine assincrono e da fabrica de sessoes do SQLAlchemy."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.db.base import Base


def create_engine(database_url: str) -> AsyncEngine:
    """Cria o engine assincrono do SQLAlchemy a partir da URL de conexao."""
    # future=True nao e mais necessario no SQLAlchemy 2, mas echo fica desligado por padrao
    return create_async_engine(database_url, echo=False)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Cria a fabrica de sessoes assincronas vinculada ao engine informado."""
    # expire_on_commit=False evita recarregar atributos apos commit, util em respostas de API
    return async_sessionmaker(engine, expire_on_commit=False)


async def init_models(engine: AsyncEngine) -> None:
    """Cria as tabelas do banco local, caso ainda nao existam."""
    # abre uma conexao assincrona para rodar o DDL de criacao das tabelas
    async with engine.begin() as conn:
        # cria todas as tabelas registradas na Base declarativa
        await conn.run_sync(Base.metadata.create_all)


@asynccontextmanager
async def session_scope(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession]:
    """Fornece uma sessao assincrona dentro de um bloco `async with`, com commit/rollback automatico."""
    # abre uma nova sessao a partir da fabrica
    async with session_factory() as session:
        try:
            # devolve a sessao para uso dentro do bloco "async with"
            yield session
            # confirma a transacao se nenhum erro ocorreu
            await session.commit()
        except Exception:
            # desfaz a transacao em caso de erro
            await session.rollback()
            # repropaga a excecao original
            raise
