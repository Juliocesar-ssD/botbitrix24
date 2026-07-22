"""Modelos Pydantic compativeis com a resposta real de GET https://open.cnpja.com/office/{cnpj}.

Estrutura validada em consulta real ao endpoint publico (ver docs/referencias-externas.md).
Todos os campos de negocio sao opcionais: a API pode alterar ou omitir campos sem aviso
previo, e o servico de enriquecimento deve tolerar ausencias sem quebrar.
"""

from pydantic import BaseModel, ConfigDict, Field


class CnpjaPais(BaseModel):
    """Pais associado a um endereco ou pessoa (ex: {"id": 76, "name": "Brasil"})."""

    model_config = ConfigDict(extra="allow")

    # id numerico do pais na base da CNPJa
    id: int | None = None
    # nome do pais
    name: str | None = None


class CnpjaEndereco(BaseModel):
    """Objeto "address" da resposta da CNPJa."""

    model_config = ConfigDict(extra="allow")

    # codigo IBGE do municipio
    municipality: int | None = None
    # logradouro (rua/avenida)
    street: str | None = None
    # numero do imovel
    number: str | None = None
    # bairro
    district: str | None = None
    # nome do municipio
    city: str | None = None
    # sigla da UF (ex: "RJ", "SP")
    state: str | None = None
    # complemento do endereco
    details: str | None = None
    # CEP, sem formatacao
    zip: str | None = None
    # pais do endereco
    country: CnpjaPais | None = None


class CnpjaEmail(BaseModel):
    """Item da lista "emails" da resposta da CNPJa (ex: {"ownership": "CORPORATE", "address": "...", "domain": "..."})."""

    model_config = ConfigDict(extra="allow")

    # titularidade do e-mail (ex: "CORPORATE", "PERSONAL"); usada para priorizar corporativos
    ownership: str | None = None
    # endereco de e-mail completo
    address: str | None = None
    # dominio do e-mail (informativo; nao usado na selecao)
    domain: str | None = None


class CnpjaPhone(BaseModel):
    """Item da lista "phones" da resposta da CNPJa (ex: {"type": "MOBILE", "area": "21", "number": "999999999"})."""

    model_config = ConfigDict(extra="allow")

    # tipo do telefone (ex: "LANDLINE", "MOBILE"); usado para traduzir o rotulo exibido
    type: str | None = None
    # DDD do telefone, sem formatacao
    area: str | None = None
    # numero do telefone, sem formatacao
    number: str | None = None


class CnpjaAtividade(BaseModel):
    """Atividade economica (CNAE), usada tanto para mainActivity quanto sideActivities."""

    model_config = ConfigDict(extra="allow")

    # codigo numerico do CNAE (ex: 6911701)
    id: int | None = None
    # descricao textual do CNAE
    text: str | None = None


class CnpjaStatus(BaseModel):
    """Situacao cadastral (objeto "status")."""

    model_config = ConfigDict(extra="allow")

    # id numerico da situacao cadastral na base da CNPJa
    id: int | None = None
    # descricao textual da situacao cadastral (ex: "Ativa")
    text: str | None = None


class CnpjaNatureza(BaseModel):
    """Natureza juridica (objeto "nature" dentro de "company")."""

    model_config = ConfigDict(extra="allow")

    # codigo numerico da natureza juridica
    id: int | None = None
    # descricao textual da natureza juridica
    text: str | None = None


class CnpjaPorte(BaseModel):
    """Porte da empresa (objeto "size" dentro de "company")."""

    model_config = ConfigDict(extra="allow")

    # id numerico do porte na base da CNPJa
    id: int | None = None
    # sigla do porte (ex: "ME", "EPP", "DEMAIS")
    acronym: str | None = None
    # descricao textual do porte
    text: str | None = None


class CnpjaCargo(BaseModel):
    """Cargo/qualificacao de um socio ou administrador (objeto "role" dentro de "members")."""

    model_config = ConfigDict(extra="allow")

    # id numerico do cargo na base da CNPJa
    id: int | None = None
    # descricao textual do cargo (ex: "Diretor", "Presidente")
    text: str | None = None


class CnpjaPessoa(BaseModel):
    """Pessoa fisica ou juridica associada a um membro do quadro societario."""

    model_config = ConfigDict(extra="allow")

    # identificador interno da pessoa na base da CNPJa
    id: str | None = None
    # tipo da pessoa: "NATURAL", "LEGAL" ou "UNKNOWN"
    type: str | None = None
    # nome da pessoa ou razao social, quando socio pessoa juridica
    name: str | None = None
    # documento (CPF/CNPJ) parcialmente mascarado pela propria API
    taxId: str | None = None
    # faixa etaria (ex: "41-50"), quando disponivel
    age: str | None = None
    # pais de origem da pessoa
    country: CnpjaPais | None = None


class CnpjaMembro(BaseModel):
    """Item do quadro societario (objeto dentro da lista "company.members").

    Observacao importante: a resposta publica NAO traz percentual de participacao
    societaria nem quotas. A regra de socio majoritario deve tratar esse cenario
    como "participacao nao informada" (ver app/services/shareholder.py).
    """

    model_config = ConfigDict(extra="allow")

    # data de entrada no quadro societario (ISO "YYYY-MM-DD"), pode ser None
    since: str | None = None
    # dados da pessoa (socio/administrador)
    person: CnpjaPessoa | None = None
    # cargo/qualificacao da pessoa nesta empresa
    role: CnpjaCargo | None = None


class CnpjaSimples(BaseModel):
    """Situacao de opcao pelo Simples Nacional ou SIMEI."""

    model_config = ConfigDict(extra="allow")

    # indica se a empresa e optante
    optant: bool | None = None
    # data de opcao, quando optante
    since: str | None = None


class CnpjaEmpresa(BaseModel):
    """Objeto "company": dados da empresa como um todo (nao do estabelecimento)."""

    model_config = ConfigDict(extra="allow")

    # identificador da empresa (raiz do CNPJ, 8 primeiros digitos)
    id: str | None = None
    # razao social da empresa
    name: str | None = None
    # capital social declarado (numero, sem formatacao)
    equity: float | None = None
    # natureza juridica
    nature: CnpjaNatureza | None = None
    # porte da empresa
    size: CnpjaPorte | None = None
    # quadro societario (lista de administradores/socios)
    members: list[CnpjaMembro] = []
    # situacao do Simples Nacional
    simples: CnpjaSimples | None = None
    # situacao do SIMEI
    simei: CnpjaSimples | None = None


class CnpjaOfficeResponse(BaseModel):
    """Resposta completa de GET /office/{cnpj} (nivel do estabelecimento)."""

    model_config = ConfigDict(extra="allow")

    # data/hora da ultima atualizacao do registro na base da CNPJa
    updated: str | None = None
    # CNPJ completo do estabelecimento (14 digitos, sem formatacao)
    taxId: str | None = None
    # nome fantasia do estabelecimento
    alias: str | None = None
    # data de abertura do estabelecimento (ISO "YYYY-MM-DD")
    founded: str | None = None
    # True se o estabelecimento e a matriz, False se e filial
    head: bool | None = None
    # dados da empresa (razao social, capital social, natureza, porte, socios)
    company: CnpjaEmpresa | None = None
    # data da situacao cadastral atual
    statusDate: str | None = None
    # situacao cadastral atual
    status: CnpjaStatus | None = None
    # endereco do estabelecimento
    address: CnpjaEndereco | None = None
    # atividade economica principal (CNAE principal)
    mainActivity: CnpjaAtividade | None = None
    # atividades economicas secundarias (nao utilizadas neste projeto)
    sideActivities: list[CnpjaAtividade] = []
    # e-mails de contato do estabelecimento (lista; pode vir vazia ou ausente)
    emails: list[CnpjaEmail] = []
    # telefones de contato do estabelecimento (lista; pode vir vazia ou ausente)
    phones: list[CnpjaPhone] = Field(default_factory=list)
