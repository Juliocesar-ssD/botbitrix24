"""Transforma a resposta da CNPJa nos valores finais dos campos do Bitrix24.

Responsavel por: normalizacao de textos (porte, situacao cadastral, matriz/filial),
resolucao de listas (enumeration) via crm.deal.fields com fallback validado,
formatacao de datas/dinheiro/CNAE/natureza juridica, e montagem do endereco e
quadro societario (delegados a app/services/address.py e app/services/shareholder.py).
"""

import re
from dataclasses import dataclass, field
from typing import Any

from app.config.bitrix_fields import BITRIX_FIELDS
from app.config.enums import (
    MATRIZ_FILIAL_FALLBACK_IDS,
    PORTE_EMPRESA_FALLBACK_IDS,
    SITUACAO_CADASTRAL_FALLBACK_IDS,
    TIPO_PESSOA_FALLBACK_IDS,
    UF_PARA_ID_BITRIX_FALLBACK,
    UF_PARA_NOME_COMPLETO,
    MatrizFilial,
    PorteEmpresa,
    SituacaoCadastral,
    TipoPessoa,
)
from app.core.utils import format_bitrix_money, normalize_text
from app.schemas.bitrix import BitrixFieldDescription
from app.schemas.cnpja import CnpjaEmail, CnpjaOfficeResponse
from app.services.address import build_full_address
from app.services.phone import build_phones_text
from app.services.shareholder import (
    SocioComParticipacao,
    build_shareholder_board_text,
    resolve_majority_shareholder,
)

# titularidade priorizada ao escolher o e-mail entre varios retornados pela CNPJa
_OWNERSHIP_CORPORATE = "CORPORATE"

# padrao simples de validacao de formato de e-mail (suficiente para descartar lixo obvio)
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _select_email(emails: list[CnpjaEmail]) -> str | None:
    """Seleciona o e-mail a ser enviado ao Bitrix a partir da lista retornada pela CNPJa.

    Prioriza o primeiro item com ownership == "CORPORATE"; na ausencia de um
    e-mail corporativo, usa o primeiro e-mail valido da lista (mantendo a ordem
    original). Remove espacos, converte para lowercase e ignora enderecos vazios
    ou com formato invalido. Retorna None se nenhum e-mail valido for encontrado
    (nesse caso o valor existente no Bitrix nao e alterado).
    """
    candidatos_validos = [
        email.address.strip().lower()
        for email in emails
        if email.address and _EMAIL_PATTERN.match(email.address.strip())
    ]
    if not candidatos_validos:
        return None

    # procura o primeiro e-mail corporativo, preservando a ordem original da lista
    for email in emails:
        if not email.address:
            continue
        endereco_normalizado = email.address.strip().lower()
        if endereco_normalizado not in candidatos_validos:
            continue
        if email.ownership and email.ownership.strip().upper() == _OWNERSHIP_CORPORATE:
            return endereco_normalizado

    # nenhum corporativo encontrado: usa o primeiro e-mail valido da lista
    return candidatos_validos[0]


@dataclass
class MappedFields:
    """Resultado da transformacao: valores por chave logica, prontos para comparar/enviar."""

    # valores finais por chave logica (ver app/config/bitrix_fields.py)
    values: dict[str, Any] = field(default_factory=dict)
    # avisos nao bloqueantes gerados durante o mapeamento
    warnings: list[str] = field(default_factory=list)


class EnumerationResolver:
    """Resolve valores logicos (ex: "ATIVA") para o ID do item de lista no Bitrix24.

    Estrategia: primeiro tenta casar pelo texto (VALUE normalizado) dos items
    retornados por crm.deal.fields; se nao encontrar, usa o ID de fallback validado.
    """

    def __init__(self, field_descriptions: dict[str, BitrixFieldDescription]) -> None:
        # descricoes de campo (com items) obtidas dinamicamente via crm.deal.fields
        self._field_descriptions = field_descriptions

    def resolve(
        self,
        field_key: str,
        candidate_labels: list[str],
        fallback_ids: dict[str, int],
        fallback_key: str,
    ) -> tuple[int | None, str | None]:
        """Tenta resolver o ID do item de lista para o campo informado.

        `candidate_labels` sao textos normalizados aceitos para casar com o VALUE
        de cada item (ex: ["MICROEMPRESA", "ME", "MICRO EMPRESA"]).
        Retorna (id_resolvido, aviso). Se nao encontrar em lugar nenhum, id e None
        e um aviso de configuracao e retornado.
        """
        # nome tecnico do campo no Bitrix (ex: UF_CRM_...)
        nome_tecnico = BITRIX_FIELDS[field_key]
        # descricao do campo, se foi retornada por crm.deal.fields
        descricao = self._field_descriptions.get(nome_tecnico)

        # tenta resolver dinamicamente pelos items retornados pelo portal
        if descricao is not None and descricao.items:
            candidatos_normalizados = {normalize_text(c) for c in candidate_labels}
            for item in descricao.items:
                if item.VALUE is None or item.ID is None:
                    continue
                if normalize_text(item.VALUE) in candidatos_normalizados:
                    return int(item.ID), None

        # fallback validado: usa o ID fixo conhecido, quando existir para a chave
        if fallback_key in fallback_ids:
            return fallback_ids[fallback_key], None

        # nao foi possivel resolver por nenhuma via - gera aviso, sem inventar ID
        return None, f"Nao foi possivel resolver o valor de lista para '{field_key}' ({fallback_key})."


def _normalize_porte(texto_api: str) -> str:
    """Normaliza o texto/sigla de porte retornado pela CNPJa para uma chave logica interna."""
    normalizado = normalize_text(texto_api)
    if normalizado in {"ME", "MICRO EMPRESA", "MICROEMPRESA"}:
        return PorteEmpresa.MICROEMPRESA.value
    if normalizado in {"EPP", "EMPRESA PEQUENO PORTE", "EMPRESA DE PEQUENO PORTE"}:
        return PorteEmpresa.EMPRESA_DE_PEQUENO_PORTE.value
    if normalizado in {"DEMAIS", "SEM ENQUADRAMENTO"}:
        return PorteEmpresa.DEMAIS.value
    return PorteEmpresa.NAO_INFORMADO.value


def _normalize_situacao_cadastral(texto_api: str | None) -> str:
    """Normaliza o texto de situacao cadastral retornado pela CNPJa para uma chave logica interna."""
    if not texto_api:
        return SituacaoCadastral.NAO_INFORMADA.value
    normalizado = normalize_text(texto_api)
    mapa = {
        "ATIVA": SituacaoCadastral.ATIVA.value,
        "SUSPENSA": SituacaoCadastral.SUSPENSA.value,
        "INAPTA": SituacaoCadastral.INAPTA.value,
        "BAIXADA": SituacaoCadastral.BAIXADA.value,
        "NULA": SituacaoCadastral.NULA.value,
    }
    return mapa.get(normalizado, SituacaoCadastral.NAO_INFORMADA.value)


def _labels_for_situacao(chave_logica: str) -> list[str]:
    """Textos candidatos aceitos na lista do Bitrix para cada situacao cadastral."""
    mapa = {
        SituacaoCadastral.ATIVA.value: ["ATIVA"],
        SituacaoCadastral.SUSPENSA.value: ["SUSPENSA"],
        SituacaoCadastral.INAPTA.value: ["INAPTA"],
        SituacaoCadastral.BAIXADA.value: ["BAIXADA"],
        SituacaoCadastral.NULA.value: ["NULA"],
        SituacaoCadastral.NAO_INFORMADA.value: ["NAO INFORMADA", "NÃO INFORMADA"],
    }
    return mapa[chave_logica]


def _labels_for_porte(chave_logica: str) -> list[str]:
    """Textos candidatos aceitos na lista do Bitrix para cada porte de empresa."""
    mapa = {
        PorteEmpresa.MICROEMPRESA.value: ["MICROEMPRESA", "ME", "MICRO EMPRESA"],
        PorteEmpresa.EMPRESA_DE_PEQUENO_PORTE.value: [
            "EMPRESA DE PEQUENO PORTE",
            "EPP",
            "EMPRESA PEQUENO PORTE",
        ],
        PorteEmpresa.DEMAIS.value: ["DEMAIS", "SEM ENQUADRAMENTO"],
        PorteEmpresa.NAO_INFORMADO.value: ["NAO INFORMADO", "NÃO INFORMADO"],
    }
    return mapa[chave_logica]


def _labels_for_matriz_filial(chave_logica: str) -> list[str]:
    """Textos candidatos aceitos na lista do Bitrix para matriz/filial."""
    mapa = {
        MatrizFilial.MATRIZ.value: ["MATRIZ"],
        MatrizFilial.FILIAL.value: ["FILIAL"],
        MatrizFilial.NAO_INFORMADA.value: ["NAO INFORMADA", "NÃO INFORMADA"],
    }
    return mapa[chave_logica]


def map_cnpja_response_to_bitrix_fields(
    cnpja_data: CnpjaOfficeResponse,
    resolver: EnumerationResolver,
    currency: str,
    fill_separate_address_fields: bool,
    today_iso: str,
) -> MappedFields:
    """Aplica todas as regras de mapeamento e retorna os valores finais por chave logica."""
    resultado = MappedFields()

    # 11.1 razao social - nunca apaga com vazio (a omissao de chave ja evita isso na comparacao)
    if cnpja_data.company and cnpja_data.company.name:
        resultado.values["razao_social"] = cnpja_data.company.name.strip()

    # 11.2 tipo de pessoa - a consulta e sempre por CNPJ, logo sempre Pessoa Juridica
    id_tipo_pessoa, aviso = resolver.resolve(
        "tipo_pessoa",
        candidate_labels=["PESSOA JURIDICA", "PESSOA JURÍDICA"],
        fallback_ids=TIPO_PESSOA_FALLBACK_IDS,
        fallback_key=TipoPessoa.PESSOA_JURIDICA.value,
    )
    if id_tipo_pessoa is not None:
        resultado.values["tipo_pessoa"] = id_tipo_pessoa
    elif aviso:
        resultado.warnings.append(aviso)

    # 11.3 nome fantasia - nunca apaga com vazio
    if cnpja_data.alias:
        resultado.values["nome_fantasia"] = cnpja_data.alias.strip()

    # e-mail de contato - prioriza ownership CORPORATE; nunca apaga com vazio/invalido
    email_selecionado = _select_email(cnpja_data.emails)
    if email_selecionado is not None:
        resultado.values["email"] = email_selecionado

    # 11.4 situacao cadastral - normaliza e resolve o ID da lista
    situacao_texto = cnpja_data.status.text if cnpja_data.status else None
    chave_situacao = _normalize_situacao_cadastral(situacao_texto)
    id_situacao, aviso = resolver.resolve(
        "situacao_cadastral",
        candidate_labels=_labels_for_situacao(chave_situacao),
        fallback_ids=SITUACAO_CADASTRAL_FALLBACK_IDS,
        fallback_key=chave_situacao,
    )
    if id_situacao is not None:
        resultado.values["situacao_cadastral"] = id_situacao
    elif aviso:
        resultado.warnings.append(aviso)

    # 11.5 data da situacao cadastral - formato ISO YYYY-MM-DD, repassado como veio
    if cnpja_data.statusDate:
        resultado.values["data_situacao_cadastral"] = cnpja_data.statusDate

    # 11.6 motivo da situacao cadastral - a resposta publica da CNPJa nao traz este campo;
    # documentado como limitacao conhecida (ver docs/referencias-externas.md). Nao enviamos
    # "null"/"undefined" nem um objeto serializado: se nao houver dado, simplesmente omitimos a chave.

    # 11.7 matriz ou filial - baseado no booleano "head"
    if cnpja_data.head is not None:
        chave_matriz_filial = MatrizFilial.MATRIZ.value if cnpja_data.head else MatrizFilial.FILIAL.value
        id_matriz_filial, aviso = resolver.resolve(
            "matriz_filial",
            candidate_labels=_labels_for_matriz_filial(chave_matriz_filial),
            fallback_ids=MATRIZ_FILIAL_FALLBACK_IDS,
            fallback_key=chave_matriz_filial,
        )
        if id_matriz_filial is not None:
            resultado.values["matriz_filial"] = id_matriz_filial
        elif aviso:
            resultado.warnings.append(aviso)

    # 11.8 porte da empresa - normaliza a partir do acronym/text retornado
    porte_bruto = None
    if cnpja_data.company and cnpja_data.company.size:
        porte_bruto = cnpja_data.company.size.acronym or cnpja_data.company.size.text
    chave_porte = _normalize_porte(porte_bruto) if porte_bruto else PorteEmpresa.NAO_INFORMADO.value
    id_porte, aviso = resolver.resolve(
        "porte_empresa",
        candidate_labels=_labels_for_porte(chave_porte),
        fallback_ids=PORTE_EMPRESA_FALLBACK_IDS,
        fallback_key=chave_porte,
    )
    if id_porte is not None:
        resultado.values["porte_empresa"] = id_porte
    elif aviso:
        resultado.warnings.append(aviso)

    # 11.9 natureza juridica - formato "CODIGO — DESCRICAO"; sem codigo, usa somente a descricao
    if cnpja_data.company and cnpja_data.company.nature and cnpja_data.company.nature.text:
        descricao_natureza = cnpja_data.company.nature.text.strip()
        codigo_natureza = cnpja_data.company.nature.id
        if codigo_natureza is not None:
            resultado.values["natureza_juridica"] = f"{codigo_natureza} — {descricao_natureza}"
        else:
            resultado.values["natureza_juridica"] = descricao_natureza

    # 11.10 capital social - campo money, formatado tecnicamente como "VALOR|MOEDA"
    if cnpja_data.company and cnpja_data.company.equity is not None:
        resultado.values["capital_social"] = format_bitrix_money(cnpja_data.company.equity, currency)

    # 11.11 CNAE principal - formato "CODIGO — DESCRICAO"
    if cnpja_data.mainActivity and cnpja_data.mainActivity.text:
        descricao_cnae = cnpja_data.mainActivity.text.strip()
        codigo_cnae = cnpja_data.mainActivity.id
        if codigo_cnae is not None:
            resultado.values["cnae_principal"] = f"{codigo_cnae} — {descricao_cnae}"
        else:
            resultado.values["cnae_principal"] = descricao_cnae

    # 11.12 data de abertura - formato ISO YYYY-MM-DD, repassado como veio
    if cnpja_data.founded:
        resultado.values["data_abertura"] = cnpja_data.founded

    # 11.13 data da ultima consulta - data local do projeto (injetada via today_iso)
    resultado.values["data_ultima_consulta"] = today_iso

    # secao 12: endereco
    endereco = cnpja_data.address
    if endereco is not None:
        if fill_separate_address_fields:
            if endereco.zip:
                resultado.values["cep"] = endereco.zip
            if endereco.street:
                resultado.values["logradouro"] = endereco.street.strip()
            if endereco.number:
                resultado.values["numero_endereco"] = endereco.number.strip()
            if endereco.details:
                resultado.values["complemento"] = endereco.details.strip()
            if endereco.district:
                resultado.values["bairro"] = endereco.district.strip()
            if endereco.city:
                resultado.values["municipio"] = endereco.city.strip()

            # estado: resolve dinamicamente pelo texto (sigla ou nome completo) e trata UF ausente
            if endereco.state:
                sigla_uf = endereco.state.strip().upper()
                nome_completo_uf = UF_PARA_NOME_COMPLETO.get(sigla_uf)
                candidatos_uf = [sigla_uf]
                if nome_completo_uf:
                    candidatos_uf.append(nome_completo_uf)
                # exclui explicitamente o rotulo antigo/duplicado "BRASILIA" da resolucao do DF
                id_estado, aviso_estado = resolver.resolve(
                    "estado",
                    candidate_labels=candidatos_uf,
                    fallback_ids=UF_PARA_ID_BITRIX_FALLBACK,
                    fallback_key=sigla_uf,
                )
                if id_estado is not None:
                    resultado.values["estado"] = id_estado
                else:
                    # UF nao cadastrada no portal (ex: SE): nao inventa ID, so avisa
                    resultado.warnings.append(
                        f"Estado '{sigla_uf}' nao encontrado na lista do Bitrix; "
                        f"campo 'estado' nao foi atualizado. {aviso_estado or ''}".strip()
                    )

        # endereco completo (texto) e sempre preenchido, independente da flag acima
        endereco_completo = build_full_address(endereco)
        if endereco_completo:
            resultado.values["endereco_completo"] = endereco_completo

    # secao 13: quadro societario
    membros = cnpja_data.company.members if cnpja_data.company else []
    texto_quadro = build_shareholder_board_text(membros)
    if texto_quadro is not None:
        resultado.values["quadro_societario"] = texto_quadro
    elif membros == [] and cnpja_data.company is not None:
        # a API respondeu mas nao trouxe quadro societario: nao apaga o que ja existe, so avisa
        resultado.warnings.append(
            "A CNPJa nao retornou quadro societario para este CNPJ; campo nao foi alterado."
        )

    # secao 14: socio majoritario
    socios_com_participacao = [
        SocioComParticipacao(nome=" ".join(m.person.name.split()), participacao_percentual=None)
        for m in membros
        if m.person and m.person.name
    ]
    resultado.values["socio_majoritario"] = resolve_majority_shareholder(socios_com_participacao)

    # telefones localizados - um por linha, com tipo traduzido; nunca apaga se a API nao retornar
    texto_telefones = build_phones_text(cnpja_data.phones)
    if texto_telefones is not None:
        resultado.values["telefones_localizados"] = texto_telefones
    else:
        # a CNPJa nao retornou nenhum telefone valido: nao apaga o campo, so avisa
        resultado.warnings.append("cnpja_phones_not_available")

    return resultado
