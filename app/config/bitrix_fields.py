"""Mapeamento central entre chaves logicas internas e IDs tecnicos de campos do Bitrix24.

Qualquer alteracao de campo customizado no portal deve ser refletida apenas aqui.
"""

# dicionario que liga cada chave logica usada no codigo ao campo tecnico (UF_CRM_* ou padrao) do Bitrix
BITRIX_FIELDS: dict[str, str] = {
    # razao social da empresa
    "razao_social": "UF_CRM_1784294122691",
    # CNPJ/CPF informado no negocio (campo de origem da consulta)
    "cnpj": "UF_CRM_1736855231889",
    # tipo de pessoa (fisica ou juridica) - lista/enumeration
    "tipo_pessoa": "UF_CRM_1784643976699",
    # data de abertura da empresa
    "data_abertura": "UF_CRM_1784645278958",
    # CNAE principal, formato "CODIGO — DESCRICAO"
    "cnae_principal": "UF_CRM_1784649999357",
    # situacao cadastral (ativa, suspensa, etc.) - lista/enumeration
    "situacao_cadastral": "UF_CRM_1784644773147",
    # data da situacao cadastral
    "data_situacao_cadastral": "UF_CRM_1784644954576",
    # motivo da situacao cadastral (texto livre)
    "motivo_situacao_cadastral": "UF_CRM_1784645016463",
    # nome fantasia da empresa
    "nome_fantasia": "UF_CRM_1784644020075",
    # e-mail de contato (prioriza ownership == "CORPORATE"; ver app/services/field_mapper.py)
    "email": "UF_CRM_1784227881933",
    # telefones localizados pela CNPJa, um por linha (label na UI: "[A] Telefones Localizados")
    "telefones_localizados": "UF_CRM_1784751137",
    # indicacao de matriz ou filial - lista/enumeration
    "matriz_filial": "UF_CRM_1784645065682",
    # porte da empresa (microempresa, EPP, demais) - lista/enumeration
    "porte_empresa": "UF_CRM_1784645122562",
    # natureza juridica, formato "CODIGO — DESCRICAO"
    "natureza_juridica": "UF_CRM_1784645158905",
    # capital social (campo do tipo money)
    "capital_social": "UF_CRM_1784645189313",
    # estado (UF) - lista/enumeration
    "estado": "UF_CRM_1736444338795",
    # CEP do endereco
    "cep": "UF_CRM_1784646973179",
    # logradouro do endereco
    "logradouro": "UF_CRM_1784647236195",
    # numero do endereco
    "numero_endereco": "UF_CRM_1784647251597",
    # complemento do endereco
    "complemento": "UF_CRM_1784647269803",
    # bairro do endereco
    "bairro": "UF_CRM_1784647293272",
    # municipio do endereco
    "municipio": "UF_CRM_1784647308586",
    # campo do tipo address com o endereco completo montado como texto
    "endereco_completo": "UF_CRM_1784647354596",
    # data da ultima consulta realizada por esta integracao (tipo date, nao datetime)
    "data_ultima_consulta": "UF_CRM_1784650085017",
    # nome do socio identificado como majoritario, conforme regras de negocio
    "socio_majoritario": "UF_CRM_1784652393809",
    # campo padrao do Bitrix usado para o quadro societario legivel (label na UI: "[A] INFORMACOES COMPLEMENTARES")
    "quadro_societario": "SOURCE_DESCRIPTION",
}

# campos que sao listas (enumeration) e portanto exigem resolucao de ID via crm.deal.fields
ENUMERATION_FIELD_KEYS: tuple[str, ...] = (
    "tipo_pessoa",
    "situacao_cadastral",
    "matriz_filial",
    "porte_empresa",
    "estado",
)

# campos que nunca devem ser apagados mesmo se o novo valor vier vazio da CNPJa
NEVER_ERASE_FIELD_KEYS: tuple[str, ...] = (
    "razao_social",
    "nome_fantasia",
    "complemento",
    "quadro_societario",
    "email",
)
