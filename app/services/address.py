"""Montagem do endereco completo (texto) a partir dos dados da CNPJa."""

from app.schemas.cnpja import CnpjaEndereco


def build_full_address(endereco: CnpjaEndereco | None) -> str | None:
    """Monta o endereco completo como texto, no formato solicitado pelo negocio.

    Exemplo: "Avenida Rio Branco, 156, Sala 802, Centro, Rio de Janeiro, RJ, CEP 20040-009, Brasil"

    Nao inclui separadores vazios: partes ausentes sao simplesmente omitidas.
    """
    # sem objeto de endereco, nao ha o que montar
    if endereco is None:
        return None

    # lista de partes do endereco, na ordem em que devem aparecer no texto final
    partes: list[str] = []

    # logradouro (rua/avenida)
    if endereco.street:
        partes.append(endereco.street.strip())
    # numero do imovel
    if endereco.number:
        partes.append(endereco.number.strip())
    # complemento (ex: "Sala 802")
    if endereco.details:
        partes.append(endereco.details.strip())
    # bairro
    if endereco.district:
        partes.append(endereco.district.strip())
    # municipio
    if endereco.city:
        partes.append(endereco.city.strip())
    # sigla da UF
    if endereco.state:
        partes.append(endereco.state.strip())
    # CEP, formatado como "CEP 00000-000" quando tiver 8 digitos
    if endereco.zip:
        partes.append(f"CEP {_formatar_cep(endereco.zip)}")
    # pais (sempre "Brasil" quando informado pela API)
    if endereco.country and endereco.country.name:
        partes.append(endereco.country.name.strip())

    # se nenhuma parte foi encontrada, nao ha endereco para montar
    if not partes:
        return None

    # junta as partes com virgula e espaco, sem gerar separadores vazios
    return ", ".join(partes)


def _formatar_cep(cep_bruto: str) -> str:
    """Formata um CEP de 8 digitos como 00000-000; retorna o valor original se nao tiver 8 digitos."""
    # remove qualquer caractere nao numerico
    digitos = "".join(c for c in cep_bruto if c.isdigit())
    # so formata se tiver exatamente 8 digitos
    if len(digitos) == 8:
        return f"{digitos[:5]}-{digitos[5:]}"
    # caso contrario, devolve o valor original sem alteracao
    return cep_bruto
