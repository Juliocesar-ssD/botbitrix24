# Mapeamento de campos do Bitrix24

Fonte da verdade em codigo: `app/config/bitrix_fields.py` (mapeamento chave logica
-> campo tecnico) e `app/services/field_mapper.py` (regras de transformacao).

| Label (interface) | ID tecnico | Tipo | Regra de preenchimento |
|---|---|---|---|
| Razao Social | `UF_CRM_1784294122691` | string | Preenchida com `company.name` da CNPJa. Nunca apagada se a API retornar vazio. |
| CNPJ | `UF_CRM_1736855231889` | string | Campo de origem da consulta; nao e escrito pela integracao. |
| Tipo de Pessoa | `UF_CRM_1784643976699` | enumeration | Sempre "Pessoa Juridica" (a consulta e sempre por CNPJ). Resolvido dinamicamente via `crm.deal.fields`, fallback ID 353. |
| Data de Abertura | `UF_CRM_1784645278958` | date | `founded` da CNPJa, formato `YYYY-MM-DD`. |
| CNAE Principal | `UF_CRM_1784649999357` | string | `mainActivity` no formato `CODIGO — DESCRICAO`. Nunca inclui CNAEs secundarios. |
| Situacao Cadastral | `UF_CRM_1784644773147` | enumeration | Normaliza `status.text`; fallback "NAO INFORMADA" quando o texto nao e reconhecido. Resolvido dinamicamente, fallback IDs 355/357/359/361/363/365. |
| Data da Situacao Cadastral | `UF_CRM_1784644954576` | date | `statusDate` da CNPJa, formato `YYYY-MM-DD`. |
| Motivo da Situacao Cadastral | `UF_CRM_1784645016463` | string | Preenchido apenas se a CNPJa informar o motivo; nunca grava "null"/"undefined"/objeto serializado. Campo nao confirmado na resposta publica atual (ver `docs/referencias-externas.md`). |
| Nome Fantasia | `UF_CRM_1784644020075` | string | `alias` da CNPJa. Nunca substitui valor existente por vazio. |
| E-mail | `UF_CRM_1784227881933` | string | Selecionado de `emails[]` da CNPJa, priorizando `ownership == "CORPORATE"`; sem corporativo, usa o primeiro e-mail valido da lista. Normalizado (trim + lowercase); enderecos vazios/invalidos sao ignorados. Nunca apaga o e-mail existente se a API nao retornar nenhum valido. |
| Matriz/Filial | `UF_CRM_1784645065682` | enumeration | Baseado no booleano `head` (true=Matriz, false=Filial). Resolvido dinamicamente, fallback IDs 367/369/371. |
| Porte da Empresa | `UF_CRM_1784645122562` | enumeration | Normaliza `company.size` (ME/EPP/DEMAIS/desconhecido) para MICROEMPRESA / EMPRESA DE PEQUENO PORTE / DEMAIS / NAO INFORMADO. Resolvido dinamicamente, fallback IDs 373/375/377/379. |
| Natureza Juridica | `UF_CRM_1784645158905` | string | `company.nature` no formato `CODIGO — DESCRICAO`; sem codigo, usa somente a descricao. |
| Capital Social | `UF_CRM_1784645189313` | money | `company.equity` formatado como `VALOR_COM_DUAS_CASAS_DECIMAIS\|MOEDA` (ex.: `98765.43\|BRL`) via `format_bitrix_money`, usando `Decimal`. Moeda padrao vem de `BITRIX_CURRENCY`. **Formato validado no portal real** (ver secao abaixo). |
| Estado (UF) | `UF_CRM_1736444338795` | enumeration | Resolvido dinamicamente pelo texto (sigla ou nome completo) via `crm.deal.fields`. DF = 145 (nunca usar o rotulo antigo "BRASILIA" = 83). UF nao cadastrada (ex.: SE) gera warning e nao atualiza o campo. |
| CEP | `UF_CRM_1784646973179` | string | `address.zip`, somente se `FILL_SEPARATE_ADDRESS_FIELDS=true`. |
| Logradouro | `UF_CRM_1784647236195` | string | `address.street`, mesma condicao acima. |
| Numero | `UF_CRM_1784647251597` | string | `address.number`, mesma condicao acima. |
| Complemento | `UF_CRM_1784647269803` | string | `address.details`; nunca apaga complemento existente se a API nao retornar. |
| Bairro | `UF_CRM_1784647293272` | string | `address.district`, mesma condicao acima. |
| Municipio | `UF_CRM_1784647308586` | string | `address.city`, mesma condicao acima. |
| Endereco Completo | `UF_CRM_1784647354596` | address | Sempre preenchido (independente da flag), texto simples: `logradouro, numero, complemento, bairro, municipio, UF, CEP XXXXX-XXX, Brasil`. Sem latitude/longitude, sem separadores vazios. |
| Data da Ultima Consulta | `UF_CRM_1784650085017` | date | Data local do servidor no momento da execucao, formato `YYYY-MM-DD`. |
| Socio Majoritario | `UF_CRM_1784652393809` | string | Ver regras detalhadas abaixo (secao "Socio majoritario"). |
| Quadro Societario ([A] INFORMACOES COMPLEMENTARES) | `SOURCE_DESCRIPTION` | string (campo padrao) | Texto legivel, uma pessoa por linha: `NOME — QUALIFICACAO — Entrada: DD/MM/AAAA`. Omite qualificacao/data quando ausentes. Nunca apaga conteudo anterior se a API nao retornar quadro societario (so emite warning). |
| Telefones Localizados ([A] Telefones Localizados) | `UF_CRM_1784751137` | string | Selecionado de `phones[]` da CNPJa. Mantem somente digitos em `area`/`number`; ignora itens sem `number`; remove duplicados comparando DDD+numero. Formato por linha: `N. (DDD) NUMERO — ROTULO` (numero de 9 digitos: `9XXXX-XXXX`; 8 digitos: `XXXX-XXXX`; sem DDD: sem parenteses). Tipo traduzido: `LANDLINE` -> `TELEFONE FIXO`, `MOBILE` -> `CELULAR`, outro/ausente -> `TELEFONE`. Nao informa confirmacao de WhatsApp (a CNPJa nao fornece esse dado). Nunca apaga o campo se a API nao retornar telefones (emite warning `cnpja_phones_not_available`). Nao preenche automaticamente o campo `[U] Numero correto do cliente`, de preenchimento manual pelo vendedor. |

## Campos de lista (enumeration): estrategia de resolucao

1. Chama `crm.deal.fields` a cada execucao (nao cacheia entre deals, pois listas
   podem mudar no portal).
2. Le os `items` de cada campo do tipo `enumeration`.
3. Normaliza o `VALUE` de cada item (remove acentos, maiuscula, colapsa espacos)
   e compara com uma lista de textos candidatos por chave logica.
4. Se casar, usa o `ID` retornado pelo portal (fonte da verdade).
5. Se nao casar com nenhum item retornado, usa o ID de fallback validado
   (tabelas em `app/config/enums.py`).
6. Se nem o fallback existir para o valor (caso do estado "SE"/Sergipe, que pode
   nao estar cadastrado), **nao inventa ID**: emite um warning e nao atualiza
   aquele campo especifico, mas continua atualizando os demais.

## Socio majoritario

A resposta publica da CNPJa nao traz percentual de participacao societaria. As
regras abaixo (implementadas em `app/services/shareholder.py`) sao aplicadas
nesta ordem:

1. **Um unico socio** -> grava o nome desse socio.
2. **Varios socios com participacao percentual objetiva informada** -> grava o
   nome do socio com a maior participacao.
3. **Empate na maior participacao** -> grava `CONTROLE SOCIETARIO IGUALITARIO`.
4. **Varios socios sem participacao informada** (cenario mais comum com a API
   publica atual) -> grava `NAO IDENTIFICADO PELA BASE PUBLICA`.
5. **Nenhum socio retornado** -> grava `NAO INFORMADO PELA BASE PUBLICA`.

Nunca e considerado majoritario automaticamente: o primeiro item da lista, o
socio-administrador, o socio mais antigo, o representante legal ou o
administrador — a qualificacao societaria nao prova participacao majoritaria.

## Capital Social (campo money) — validado no portal real

O formato tecnico do campo `Capital Social` (`UF_CRM_1784645189313`, tipo `money`)
foi **confirmado em um portal Bitrix24 real**, por tres vias:

1. **Leitura via `crm.deal.get`**: o campo retornou no formato
   `123456.78|BRL`.
2. **Escrita via `crm.deal.update`**: o valor `98765.43|BRL` foi aceito com
   sucesso.
3. **Conferencia visual no card do negocio**: a interface exibiu corretamente
   `R$ 98.765,43`, confirmando que o Bitrix e responsavel por toda a formatacao
   visual (simbolo de moeda, separador de milhar, virgula decimal) — o payload
   enviado pela integracao nunca deve conter essa formatacao.

Regras aplicadas por `format_bitrix_money` (`app/core/utils.py`):

- Formato: `VALOR_COM_DUAS_CASAS_DECIMAIS|MOEDA` (ex.: `98765.43|BRL`).
- Usa `Decimal` (nunca `float` puro) para evitar erros de arredondamento de
  ponto flutuante; arredondamento por `ROUND_HALF_UP` para duas casas decimais.
- Sem simbolo de moeda (`R$`) no payload.
- Sem separador de milhar no payload.
- Separador decimal sempre `.` (ponto).
- Sempre exatamente duas casas decimais, mesmo para valores inteiros (`0` ->
  `0.00`, `2500` -> `2500.00`).
- A moeda enviada vem sempre de `BITRIX_CURRENCY` (padrao `BRL`), nunca hardcoded.

Nao ha mais pendencia de validacao para este campo.

## Regra geral: nunca apagar dados com valores vazios

`app/core/utils.py::remove_empty_values` remove `None`, strings vazias e listas
vazias antes de montar o payload de atualizacao. Valores `False` e `0` sao
mantidos (sao validos de negocio). Campos marcados em
`NEVER_ERASE_FIELD_KEYS` (`razao_social`, `nome_fantasia`, `complemento`,
`quadro_societario`) tem protecao adicional: mesmo que o valor atual no Bitrix
exista e a CNPJa nao retorne nada, o campo e mantido inalterado (aparece em
`fields_unchanged`, nunca em `fields_changed`).
