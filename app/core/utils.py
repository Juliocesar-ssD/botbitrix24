"""Funcoes utilitarias puras: limpeza/validacao de documentos, normalizacao de texto e valores."""

import re
import unicodedata
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.core.exceptions import InvalidCnpjError

# pesos usados no calculo dos dois digitos verificadores do CNPJ
_PESOS_PRIMEIRO_DIGITO = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
_PESOS_SEGUNDO_DIGITO = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]


def clean_document(raw_value: str) -> str:
    """Remove pontos, barras, espacos, tracos e qualquer caractere nao numerico do documento."""
    # mantem somente digitos (0-9)
    return re.sub(r"\D", "", raw_value or "")


def _calcular_digito_verificador(digitos: str, pesos: list[int]) -> int:
    """Calcula um digito verificador de CNPJ a partir dos digitos e pesos informados."""
    # soma o produto de cada digito pelo peso correspondente
    soma = sum(int(digito) * peso for digito, peso in zip(digitos, pesos, strict=True))
    # calcula o resto da divisao por 11
    resto = soma % 11
    # se o resto for menor que 2, o digito verificador e 0; senao, e 11 - resto
    return 0 if resto < 2 else 11 - resto


def is_valid_cnpj(cnpj: str) -> bool:
    """Valida se uma string de 14 digitos e um CNPJ com digitos verificadores corretos."""
    # CNPJ deve ter exatamente 14 digitos numericos
    if len(cnpj) != 14 or not cnpj.isdigit():
        return False
    # rejeita sequencias de digitos repetidos (ex: 00000000000000), que passariam no calculo
    if cnpj == cnpj[0] * 14:
        return False
    # calcula o primeiro digito verificador a partir dos 12 primeiros digitos
    primeiro_digito = _calcular_digito_verificador(cnpj[:12], _PESOS_PRIMEIRO_DIGITO)
    # calcula o segundo digito verificador a partir dos 12 primeiros + o primeiro digito calculado
    segundo_digito = _calcular_digito_verificador(cnpj[:12] + str(primeiro_digito), _PESOS_SEGUNDO_DIGITO)
    # compara os digitos calculados com os digitos informados (posicoes 12 e 13)
    return cnpj[12] == str(primeiro_digito) and cnpj[13] == str(segundo_digito)


def validate_cnpj(raw_value: str) -> str:
    """Limpa e valida um CNPJ, retornando os 14 digitos ou levantando InvalidCnpjError."""
    # remove formatacao do valor bruto
    documento = clean_document(raw_value)
    # documento vazio nao e um CNPJ valido
    if not documento:
        raise InvalidCnpjError("CNPJ ausente no campo do negocio.")
    # CNPJ deve ter 14 digitos (CPF, com 11 digitos, nao e aceito neste fluxo)
    if len(documento) != 14:
        raise InvalidCnpjError(f"Documento com {len(documento)} digitos; esperado CNPJ com 14 digitos.")
    # valida os digitos verificadores
    if not is_valid_cnpj(documento):
        raise InvalidCnpjError("CNPJ com digitos verificadores invalidos.")
    # retorna o CNPJ limpo e validado
    return documento


def normalize_text(value: str) -> str:
    """Normaliza texto para comparacao: remove acentos, maiusculiza, colapsa espacos."""
    # decompoe caracteres acentuados em letra base + acento
    sem_acento = unicodedata.normalize("NFKD", value)
    # remove os caracteres de acentuacao (categoria Mn)
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    # converte para maiusculas
    maiusculo = sem_acento.upper()
    # colapsa espacos duplicados/tabs/quebras de linha em um unico espaco
    colapsado = re.sub(r"\s+", " ", maiusculo)
    # remove espacos nas bordas
    return colapsado.strip()


def remove_empty_values(fields: dict[str, Any]) -> dict[str, Any]:
    """Remove do dicionario valores None, string vazia e listas vazias.

    Valores False e 0 sao mantidos, pois sao valores validos de negocio.
    """
    resultado: dict[str, Any] = {}
    # percorre cada par chave/valor do dicionario original
    for chave, valor in fields.items():
        # descarta valores None
        if valor is None:
            continue
        # descarta strings vazias (mas mantem strings com conteudo, incluindo "0")
        if isinstance(valor, str) and valor.strip() == "":
            continue
        # descarta listas ou tuplas vazias
        if isinstance(valor, list | tuple) and len(valor) == 0:
            continue
        # mantem o valor (incluindo False e 0, que sao validos)
        resultado[chave] = valor
    return resultado


def format_bitrix_money(value: float, currency: str) -> str:
    """Formata um valor numerico para o formato tecnico aceito pelo campo money do Bitrix24.

    Formato validado no portal real (leitura via crm.deal.get e escrita via
    crm.deal.update no campo Capital Social, UF_CRM_1784645189313): sempre
    "VALOR_COM_DUAS_CASAS_DECIMAIS|MOEDA", com ponto como separador decimal,
    sem separador de milhar e sem simbolo de moeda (ex: "98765.43|BRL"). O
    Bitrix e responsavel por exibir o valor formatado na interface (ex:
    "R$ 98.765,43"); este payload nunca deve conter essa formatacao visual.

    Usa Decimal (em vez de float) para evitar erros de ponto flutuante ao
    arredondar valores de dinheiro.
    """
    # converte via str(value) para nao herdar erros de representacao binaria de float
    valor_decimal = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    # monta o formato tecnico "VALOR|MOEDA" exigido pelo campo money
    return f"{valor_decimal}|{currency}"
