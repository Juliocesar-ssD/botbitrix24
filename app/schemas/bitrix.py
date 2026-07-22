"""Modelos Pydantic para as respostas da API REST do Bitrix24 usadas nesta integracao."""

from typing import Any

from pydantic import BaseModel, ConfigDict


class BitrixApiResponse(BaseModel):
    """Envelope generico de resposta do Bitrix24 (sucesso ou erro)."""

    model_config = ConfigDict(extra="allow")

    # payload de sucesso (formato varia por metodo: dict para .get, bool para .update)
    result: Any | None = None
    # codigo de erro retornado pelo Bitrix, quando a chamada falha
    error: str | None = None
    # descricao textual do erro retornado pelo Bitrix, quando a chamada falha
    error_description: str | None = None

    @property
    def is_error(self) -> bool:
        """Indica se a resposta representa um erro do Bitrix (campo "error" presente)."""
        # o Bitrix so inclui o campo "error" quando a chamada falha
        return self.error is not None


class BitrixFieldItem(BaseModel):
    """Item de uma lista (enumeration) dentro da descricao de um campo de crm.deal.fields."""

    model_config = ConfigDict(extra="allow")

    # ID tecnico do item da lista, usado ao enviar o valor no update
    ID: str | int | None = None
    # texto/rotulo do item, exibido na interface do Bitrix
    VALUE: str | None = None


class BitrixFieldDescription(BaseModel):
    """Descricao de um campo do Negocio, conforme retornado por crm.deal.fields."""

    model_config = ConfigDict(extra="allow")

    # tipo tecnico do campo (ex: "string", "double", "date", "enumeration", "address")
    type: str | None = None
    # rotulo do campo exibido na interface
    title: str | None = None
    # itens da lista, presentes apenas quando type == "enumeration"
    items: list[BitrixFieldItem] | None = None
