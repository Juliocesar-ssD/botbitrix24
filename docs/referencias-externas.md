# Referencias externas

Este documento reune links, finalidade e notas tecnicas das APIs externas usadas
nesta integracao. Nao reproduz as documentacoes originais na integra: guarda apenas
o resumo necessario para manter o codigo. **Sempre que a estrutura de resposta de
qualquer uma dessas APIs mudar, consulte a documentacao oficial (links abaixo)
antes de alterar os modelos ou os mapeamentos.**

## CNPJa (API publica "open")

| Link | Finalidade |
|---|---|
| https://cnpja.com/api/open | Visao geral da API publica gratuita da CNPJa (tier "open"). |
| https://cnpja.com/api/open/reference | Referencia dos endpoints e estrutura de resposta. |

**Endpoint utilizado:** `GET https://open.cnpja.com/office/{cnpj}`

- Nao exige token/autenticacao para o tier publico.
- CNPJ enviado sem formatacao (14 digitos).

### Estrutura de resposta (validada empiricamente)

A estrutura abaixo foi confirmada com chamadas reais ao endpoint publico (CNPJs de
empresas conhecidas). A pagina de referencia oficial retornou HTTP 429 durante a
pesquisa que originou este projeto, entao alguns campos (ex.: motivo da situacao
cadastral, percentual de participacao societaria) **nao puderam ser confirmados
como existentes** e sao tratados como ausentes/opcionais no codigo:

```
{
  "updated": "2024-...",
  "taxId": "00000000000191",
  "alias": "Nome fantasia" | null,
  "founded": "YYYY-MM-DD",
  "head": true | false,               // true = matriz, false = filial
  "statusDate": "YYYY-MM-DD",
  "status": { "id": 1, "text": "Ativa" },
  "address": {
    "municipality": 3304557,
    "street": "...", "number": "...", "district": "...",
    "city": "...", "state": "RJ", "details": "..." | null,
    "zip": "...", "country": { "id": 76, "name": "Brasil" }
  },
  "mainActivity": { "id": 6911701, "text": "Servicos advocaticios" },
  "sideActivities": [ { "id": ..., "text": "..." } ],
  "company": {
    "id": "00000000",
    "name": "Razao social",
    "equity": 100000.0,
    "nature": { "id": 2062, "text": "Sociedade Empresaria Limitada" },
    "size": { "id": 1, "acronym": "DEMAIS", "text": "Demais" },
    "members": [
      {
        "since": "YYYY-MM-DD" | null,
        "person": { "id": "uuid", "type": "NATURAL", "name": "...", "taxId": null, "age": "41-50" },
        "role": { "id": 1, "text": "Socio-Administrador" }
      }
    ]
  }
}
```

### Limites conhecidos

- **Nao ha confirmacao numerica oficial do limite de requisicoes do tier gratuito**
  (a documentacao retornou HTTP 429 durante a consulta). Por seguranca, este
  projeto aplica um limite **local e configuravel** de `MAX_CNPJA_REQUESTS_PER_MINUTE`
  (padrao: 5/min) via janela deslizante, alem de respeitar o header `Retry-After`
  quando a propria API responde HTTP 429.
- A resposta publica **nao traz percentual/quotas de participacao societaria**.
  Por isso a regra de socio majoritario trata "varios socios sem percentual
  informado" como o cenario mais comum na pratica (ver `docs/mapeamento-bitrix.md`
  e `app/services/shareholder.py`).
- A resposta **nao traz latitude/longitude** de forma confiavel; este projeto nunca
  envia coordenadas para o Bitrix (não inventa `0;0`).
- O campo "motivo da situacao cadastral" nao apareceu em nenhuma amostra observada
  (todas as empresas testadas estavam com situacao "Ativa"); o codigo trata esse
  dado como possivelmente ausente e nunca escreve "null"/"None" no Bitrix.

> **Nota:** sempre que a CNPJa alterar a estrutura do JSON de resposta, revalide
> os modelos em `app/schemas/cnpja.py` contra `https://cnpja.com/api/open/reference`
> e contra uma chamada real ao endpoint antes de alterar `app/services/field_mapper.py`.

## Bitrix24 (REST via webhook de entrada)

| Link | Finalidade |
|---|---|
| https://apidocs.bitrix24.com/api-reference/crm/deals/crm-deal-get.html | Metodo `crm.deal.get`, usado para ler os campos atuais do negocio. |
| https://apidocs.bitrix24.com/api-reference/crm/deals/crm-deal-fields.html | Metodo `crm.deal.fields`, usado para resolver dinamicamente os IDs das listas (enumeration). |
| https://apidocs.bitrix24.com/api-reference/crm/deals/crm-deal-update.html | Metodo `crm.deal.update`, usado para gravar somente os campos alterados. |
| https://apidocs.bitrix24.com/api-reference/crm/universal/crm-item-update.html | Metodo universal `crm.item.update` (Smart Process/CRM universal), candidato a futura migracao. |

### Observacao sobre `crm.deal.update` vs `crm.item.update`

Esta integracao usa **`crm.deal.get` / `crm.deal.fields` / `crm.deal.update`**
porque foram os metodos validados neste portal (testados manualmente com um
negocio real). O `BitrixClient` (`app/clients/bitrix.py`) concentra toda chamada
REST ao Bitrix em uma unica classe — nenhuma outra parte do sistema monta URLs ou
chama `httpx` diretamente contra o Bitrix. Isso foi feito deliberadamente para que
uma futura migracao para os metodos universais `crm.item.get` / `crm.item.update`
(necessarios caso o funil vire um Smart Process / CRM universal) exija alterar
apenas este cliente, sem tocar em `services/` ou `api/routes/`.

### Limites conhecidos

- Webhooks de entrada do Bitrix24 tem limite de chamadas por segundo definido pelo
  proprio portal (variavel por plano); o `BitrixClient` trata HTTP 5xx como erro
  transitorio (retry com backoff exponencial, ate 3 tentativas) e nunca repete
  automaticamente erros de validacao (campo `error` no corpo da resposta).
- O Bitrix sempre responde HTTP 200 mesmo em erros de aplicacao — o corpo JSON
  precisa ser inspecionado (`error` / `error_description`). O cliente nunca
  considera HTTP 200 como sucesso sem essa checagem.

> **Nota:** sempre que a estrutura de `crm.deal.fields` ou o formato de campos
> especiais (money, date, address) mudar, revalide contra a documentacao oficial
> acima antes de alterar `app/services/field_mapper.py` ou `app/services/address.py`.
