"""Base declarativa do SQLAlchemy usada por todos os modelos ORM."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Classe base declarativa compartilhada por todos os modelos ORM da aplicacao."""
