# Integracao Bitrix24 <-> CNPJa

API interna que recebe o ID de um Negocio (`deal`) do Bitrix24, consulta o
CNPJ registrado nesse negocio na API publica da [CNPJa](https://cnpja.com/api/open),
e atualiza automaticamente os campos cadastrais do negocio — somente os campos
que realmente mudaram.

## Objetivo

1. Receber `deal_id`.
2. Consultar o negocio via `crm.deal.get`.
3. Ler o CNPJ do campo `UF_CRM_1736855231889`.
4. Limpar e validar o CNPJ (14 digitos + digitos verificadores).
5. Consultar `GET https://open.cnpja.com/office/{cnpj}`.
6. Normalizar os dados (situacao cadastral, porte, matriz/filial, endereco,
   quadro societario, socio majoritario, etc.).
7. Resolver os campos de lista (enumeration) dinamicamente via `crm.deal.fields`.
8. Comparar com os valores atuais do negocio.
9. Atualizar via `crm.deal.update` somente os campos alterados.
10. Registrar a execucao (idempotencia + auditoria) em SQLite local.
11. Retornar um relatorio detalhado da execucao.

## Arquitetura

```
app/
  main.py                 # FastAPI app, lifespan (http client, engine, locks)
  api/
    dependencies.py       # DI: settings, clients, sessao de banco, seguranca
    routes/health.py      # GET /health
    routes/cnpj.py         # POST /enrich-deal, GET /syncs/{deal_id}
  clients/
    bitrix.py              # BitrixClient (crm.deal.get/fields/update)
    cnpja.py                # CnpjaClient (rate limit local + retries)
  config/
    settings.py            # pydantic-settings (variaveis de ambiente)
    bitrix_fields.py        # mapeamento chave logica -> campo tecnico
    enums.py                # enums internos + fallback de IDs de lista/UF
  db/
    base.py, models.py, session.py   # SQLAlchemy 2 assincrono (SQLite)
  schemas/
    requests.py, responses.py         # contratos da API interna
    bitrix.py, cnpja.py                # contratos das APIs externas
  services/
    field_mapper.py         # normalizacao + resolucao de listas
    address.py               # montagem do endereco completo (texto)
    shareholder.py            # quadro societario + socio majoritario
    idempotency.py            # lock por deal_id + checagem de TTL
    enrichment.py              # orquestracao do fluxo completo
  core/
    exceptions.py, logging.py, security.py, utils.py
```

O `BitrixClient` concentra toda chamada REST ao Bitrix, isolando o restante do
sistema do metodo exato usado (`crm.deal.*` hoje; `crm.item.*` no futuro — ver
secao "Migracao futura" abaixo).

## Fluxo

Ver [docs/fluxo-integracao.md](docs/fluxo-integracao.md) para o diagrama completo
do fluxo, idempotencia, `dry_run` e mapa de excecoes -> codigos HTTP.

## Instalacao local (sem Docker)

Pre-requisitos: Python 3.12.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

Copie `.env.example` para `.env` e preencha as variaveis (ver secao abaixo):

```powershell
Copy-Item .env.example .env
```

Rode a aplicacao:

```powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

A API estara em `http://localhost:8000`. Documentacao interativa (Swagger) em
`http://localhost:8000/docs`.

## Configuracao do `.env`

| Variavel | Descricao |
|---|---|
| `BITRIX_WEBHOOK_BASE_URL` | Base do webhook de entrada, **sem** o nome do metodo. Formato: `https://SEUPORTAL.bitrix24.com.br/rest/USUARIO/TOKEN`. |
| `INTEGRATION_API_KEY` | Chave exigida no header `X-Integration-Key` para chamar esta API. |
| `CNPJA_BASE_URL` | Base da API publica da CNPJa (padrao: `https://open.cnpja.com`). |
| `DATABASE_URL` | Conexao assincrona do SQLite (padrao: `sqlite+aiosqlite:///./data/cnpj_sync.db`). |
| `HTTP_TIMEOUT_SECONDS` | Timeout (segundos) para chamadas HTTP externas. |
| `MAX_CNPJA_REQUESTS_PER_MINUTE` | Limite local de consultas/minuto a CNPJa (padrao: 5). |
| `LOG_LEVEL` | Nivel de log (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |
| `FILL_SEPARATE_ADDRESS_FIELDS` | Se `true`, preenche tambem os campos individuais de endereco (alem do campo `address` completo). |
| `BITRIX_CURRENCY` | Moeda usada ao formatar o campo `money` do capital social (padrao: `BRL`). |
| `SYNC_TTL_HOURS` | Horas de validade de uma sincronizacao antes de permitir nova consulta sem `force=true`. |

**Nunca** commite o `.env` real — apenas `.env.example` (sem segredos) vai para o
repositorio. `.gitignore` ja exclui `.env` e o arquivo do banco SQLite.

## Execucao com Docker

```powershell
Copy-Item .env.example .env
# edite o .env com o webhook real e a chave de integracao
docker compose up --build
```

A API sobe em `http://localhost:8000`. O volume `./data` persiste o SQLite fora
do container.

## Execucao sem Docker (resumo)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

## Testes

```powershell
pytest
```

Os testes usam `httpx.MockTransport` para simular o Bitrix24 e a CNPJa — **nenhum
teste acessa APIs reais**. Cobrem: limpeza/validacao de CNPJ, mapeamento de campos,
listas (situacao/porte/matriz-filial/UF incluindo DF=145 e SE sem cadastro),
endereco, quadro societario, todas as regras de socio majoritario, rate limit e
HTTP 429/timeout da CNPJa, `dry_run`, update sem alteracoes, autenticacao invalida
e mascaramento de logs.

Qualidade de codigo:

```powershell
ruff check .
mypy app
```

## Exemplo de chamada

```bash
curl -X POST "http://localhost:8000/api/v1/cnpj/enrich-deal" \
  -H "Content-Type: application/json" \
  -H "X-Integration-Key: TROQUE_PELA_CHAVE" \
  -d '{
    "deal_id": 61229,
    "force": false,
    "dry_run": true
  }'
```

Resposta esperada:

```json
{
  "success": true,
  "deal_id": 61229,
  "cnpj": "00000000000191",
  "dry_run": true,
  "fields_changed": ["razao_social", "situacao_cadastral"],
  "fields_unchanged": ["nome_fantasia", "cnae_principal"],
  "warnings": [],
  "source": "CNPJá API Pública"
}
```

Historico de sincronizacoes de um negocio:

```bash
curl "http://localhost:8000/api/v1/cnpj/syncs/61229" \
  -H "X-Integration-Key: TROQUE_PELA_CHAVE"
```

## Como configurar o robo do Bitrix24

1. No portal, acesse **Aplicativos -> Webhooks -> Webhook de entrada**.
2. Crie um webhook com permissao de leitura e escrita em CRM (`crm`).
3. Copie a URL gerada; a parte `https://SEUPORTAL.bitrix24.com.br/rest/USUARIO/TOKEN`
   (sem o nome do metodo no final) e o valor de `BITRIX_WEBHOOK_BASE_URL`.
4. Configure um robo (automacao) ou processo de negocio no funil desejado para
   chamar esta API (`POST /api/v1/cnpj/enrich-deal`) passando o `deal_id` do
   negocio corrente, com o header `X-Integration-Key`.
5. Recomenda-se dry_run=true na primeira validacao em producao para conferir o
   relatorio antes de permitir escrita automatica.

### Como gerar um novo webhook

Repita os passos acima sempre que precisar rotacionar o token. Atualize apenas
a variavel `BITRIX_WEBHOOK_BASE_URL` no `.env` (ou no secret manager usado em
producao) e reinicie a aplicacao — nenhum outro arquivo precisa mudar.

### Recomendacao de seguranca

**Nunca exponha o webhook do Bitrix24 publicamente.** Esta API deve rodar em
rede interna ou atras de um proxy/API gateway que exija autenticacao adicional.
O header `X-Integration-Key` protege apenas esta API interna — ele nao substitui
o cuidado de manter o webhook do Bitrix fora de alcance publico. Segredos nunca
aparecem em logs (ver `app/core/security.py`: `mask_webhook_url`, `mask_cnpj`,
`mask_secret`).

## Tabela de campos

Ver [docs/mapeamento-bitrix.md](docs/mapeamento-bitrix.md) para a tabela completa
(label, ID tecnico, tipo, regra de preenchimento) e
[docs/referencias-externas.md](docs/referencias-externas.md) para links e notas
tecnicas das APIs externas.

### Capital Social — formato validado no portal real

O campo `Capital Social` (`UF_CRM_1784645189313`, tipo `money`) teve seu formato
**confirmado em um portal Bitrix24 real**: leitura via `crm.deal.get` (retornou
`123456.78|BRL`), escrita via `crm.deal.update` (aceitou `98765.43|BRL`) e
conferencia visual no card do negocio (exibiu `R$ 98.765,43`). `format_bitrix_money`
(`app/core/utils.py`) usa `Decimal` para montar sempre
`VALOR_COM_DUAS_CASAS_DECIMAIS|MOEDA`, sem simbolo de moeda, sem separador de
milhar e com ponto decimal — a moeda vem de `BITRIX_CURRENCY`. Detalhes completos
em [docs/mapeamento-bitrix.md](docs/mapeamento-bitrix.md#capital-social-campo-money--validado-no-portal-real).

## Limitacoes da API publica da CNPJa

- Nao ha confirmacao oficial do rate limit exato do tier gratuito; este projeto
  aplica um limite local conservador e configuravel (`MAX_CNPJA_REQUESTS_PER_MINUTE`).
- Nao retorna percentual/quotas de participacao societaria (impacta a regra de
  socio majoritario — ver abaixo).
- Nao deve ser considerada fonte de latitude/longitude.
- O campo "motivo da situacao cadastral" nao foi observado nas amostras usadas
  para construir este projeto; tratado como opcional.

## Tratamento do socio majoritario

Como a API publica normalmente nao informa participacao societaria, a regra
(ver `app/services/shareholder.py`) e:

1. Um unico socio -> esse socio.
2. Varios socios com percentual informado -> o de maior percentual.
3. Empate no percentual -> `CONTROLE SOCIETARIO IGUALITARIO`.
4. Varios socios sem percentual informado (cenario mais comum na pratica) ->
   `NAO IDENTIFICADO PELA BASE PUBLICA`.
5. Nenhum socio retornado -> `NAO INFORMADO PELA BASE PUBLICA`.

Nunca assume automaticamente que o primeiro socio, o socio-administrador, o mais
antigo ou o representante legal e o majoritario.

## Futura migracao para `crm.item.update`

O `BitrixClient` (`app/clients/bitrix.py`) e o unico ponto do sistema que conhece
os nomes dos metodos REST do Bitrix (`crm.deal.get.json`, `crm.deal.fields.json`,
`crm.deal.update.json`). Caso o funil migre para um CRM universal / Smart Process,
a troca para `crm.item.get` / `crm.item.update` deve ser feita **apenas dentro
desta classe** — `app/services/enrichment.py` e as rotas em `app/api/routes/`
nao precisam mudar, pois dependem apenas da interface (`get_deal`,
`get_deal_fields`, `update_deal`).
