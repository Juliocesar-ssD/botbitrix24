"""Enums internos e tabelas de fallback para campos de lista (enumeration) do Bitrix24.

A estrategia principal de resolucao e dinamica (via crm.deal.fields). Estas tabelas
sao usadas apenas como fallback validado quando a resolucao dinamica falhar,
e como base para os testes.
"""

from enum import StrEnum


class TipoPessoa(StrEnum):
    """Chaves logicas para o campo tipo_pessoa."""

    # pessoa fisica
    PESSOA_FISICA = "PESSOA_FISICA"
    # pessoa juridica
    PESSOA_JURIDICA = "PESSOA_JURIDICA"


class SituacaoCadastral(StrEnum):
    """Chaves logicas para o campo situacao_cadastral."""

    # empresa ativa
    ATIVA = "ATIVA"
    # empresa suspensa
    SUSPENSA = "SUSPENSA"
    # empresa inapta
    INAPTA = "INAPTA"
    # empresa baixada
    BAIXADA = "BAIXADA"
    # empresa nula
    NULA = "NULA"
    # situacao nao informada / nao reconhecida
    NAO_INFORMADA = "NAO_INFORMADA"


class MatrizFilial(StrEnum):
    """Chaves logicas para o campo matriz_filial."""

    # estabelecimento matriz
    MATRIZ = "MATRIZ"
    # estabelecimento filial
    FILIAL = "FILIAL"
    # nao informado
    NAO_INFORMADA = "NAO_INFORMADA"


class PorteEmpresa(StrEnum):
    """Chaves logicas para o campo porte_empresa."""

    # microempresa (ME)
    MICROEMPRESA = "MICROEMPRESA"
    # empresa de pequeno porte (EPP)
    EMPRESA_DE_PEQUENO_PORTE = "EMPRESA_DE_PEQUENO_PORTE"
    # demais portes / sem enquadramento
    DEMAIS = "DEMAIS"
    # porte nao informado
    NAO_INFORMADO = "NAO_INFORMADO"


# fallback validado: ID do item de lista no Bitrix24 para tipo de pessoa
TIPO_PESSOA_FALLBACK_IDS: dict[str, int] = {
    TipoPessoa.PESSOA_FISICA.value: 351,
    TipoPessoa.PESSOA_JURIDICA.value: 353,
}

# fallback validado: ID do item de lista no Bitrix24 para situacao cadastral
SITUACAO_CADASTRAL_FALLBACK_IDS: dict[str, int] = {
    SituacaoCadastral.ATIVA.value: 355,
    SituacaoCadastral.SUSPENSA.value: 357,
    SituacaoCadastral.INAPTA.value: 359,
    SituacaoCadastral.BAIXADA.value: 361,
    SituacaoCadastral.NULA.value: 363,
    SituacaoCadastral.NAO_INFORMADA.value: 365,
}

# fallback validado: ID do item de lista no Bitrix24 para matriz/filial
MATRIZ_FILIAL_FALLBACK_IDS: dict[str, int] = {
    MatrizFilial.MATRIZ.value: 367,
    MatrizFilial.FILIAL.value: 369,
    MatrizFilial.NAO_INFORMADA.value: 371,
}

# fallback validado: ID do item de lista no Bitrix24 para porte da empresa
PORTE_EMPRESA_FALLBACK_IDS: dict[str, int] = {
    PorteEmpresa.MICROEMPRESA.value: 373,
    PorteEmpresa.EMPRESA_DE_PEQUENO_PORTE.value: 375,
    PorteEmpresa.DEMAIS.value: 377,
    PorteEmpresa.NAO_INFORMADO.value: 379,
}

# fallback validado: ID do item de lista no Bitrix24 para cada UF (sigla -> ID)
# observacao: DF = 145 (nao usar o item "BRASILIA" = 83, que e um rotulo antigo duplicado)
# observacao: "SE" (Sergipe) pode nao estar cadastrado na lista do portal - tratar como warning, nao inventar ID
UF_PARA_ID_BITRIX_FALLBACK: dict[str, int] = {
    "AC": 75,
    "AL": 69,
    "AP": 79,
    "AM": 63,
    "BA": 47,
    "CE": 81,
    "DF": 145,
    "ES": 49,
    "GO": 65,
    "MA": 55,
    "MT": 51,
    "MS": 57,
    "MG": 59,
    "PA": 61,
    "PB": 77,
    "PR": 131,
    "PE": 67,
    "PI": 71,
    "RJ": 45,
    "RN": 73,
    "RS": 139,
    "RO": 53,
    "RR": 133,
    "SC": 147,
    "SP": 127,
    "TO": 129,
}

# tabela estatica UF -> nome completo, usada para casar com o texto dos items retornados por crm.deal.fields
UF_PARA_NOME_COMPLETO: dict[str, str] = {
    "AC": "ACRE",
    "AL": "ALAGOAS",
    "AP": "AMAPA",
    "AM": "AMAZONAS",
    "BA": "BAHIA",
    "CE": "CEARA",
    "DF": "DISTRITO FEDERAL",
    "ES": "ESPIRITO SANTO",
    "GO": "GOIAS",
    "MA": "MARANHAO",
    "MT": "MATO GROSSO",
    "MS": "MATO GROSSO DO SUL",
    "MG": "MINAS GERAIS",
    "PA": "PARA",
    "PB": "PARAIBA",
    "PR": "PARANA",
    "PE": "PERNAMBUCO",
    "PI": "PIAUI",
    "RJ": "RIO DE JANEIRO",
    "RN": "RIO GRANDE DO NORTE",
    "RS": "RIO GRANDE DO SUL",
    "RO": "RONDONIA",
    "RR": "RORAIMA",
    "SC": "SANTA CATARINA",
    "SP": "SAO PAULO",
    "SE": "SERGIPE",
    "TO": "TOCANTINS",
}

# rotulo antigo/duplicado que nunca deve ser escolhido para o Distrito Federal
DISTRITO_FEDERAL_ROTULO_INVALIDO = "BRASILIA"
