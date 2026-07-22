# Fluxo da integracao

## Visao geral

```
Cliente interno (ex.: robo/automacao do Bitrix24)
        |
        v
POST /api/v1/cnpj/enrich-deal   (X-Integration-Key)
        |
        v
+-------------------------------------------------------------+
| EnrichmentService.enrich_deal(deal_id, force, dry_run)       |
|                                                               |
| 1. Lock por deal_id (DealLockRegistry)                        |
|    -> segunda chamada concorrente para o mesmo deal_id        |
|       recebe HTTP 409 imediatamente.                          |
|                                                               |
| 2. BitrixClient.get_deal(deal_id)  [crm.deal.get]              |
|                                                               |
| 3. Extrai UF_CRM_1736855231889, limpa e valida o CNPJ          |
|    (14 digitos + digitos verificadores).                      |
|    -> invalido: HTTP 400, nao chega a consultar nada externo.  |
|                                                               |
| 4. Se force=False: verifica no SQLite (cnpj_sync_log) se ha    |
|    sincronizacao "success" recente (SYNC_TTL_HOURS) para o     |
|    mesmo deal_id + CNPJ. Se houver, retorna sem consultar de    |
|    novo a CNPJa nem o Bitrix.                                  |
|                                                               |
| 5. CnpjaClient.get_office(cnpj)  [GET /office/{cnpj}]          |
|    -> rate limit local (sliding window, MAX_CNPJA_REQUESTS_    |
|       PER_MINUTE), retry com backoff em erros transitorios,    |
|       respeita Retry-After em HTTP 429, nao repete 400/404.    |
|                                                               |
| 6. BitrixClient.resolve_enumeration_fields([...])              |
|    [crm.deal.fields] -> resolve dinamicamente os IDs das       |
|    listas (tipo_pessoa, situacao_cadastral, matriz_filial,     |
|    porte_empresa, estado), com fallback validado.              |
|                                                               |
| 7. field_mapper.map_cnpja_response_to_bitrix_fields(...)       |
|    -> aplica todas as regras de formatacao/normalizacao        |
|       (datas ISO, money tecnico, CNAE/natureza "CODIGO —       |
|       DESCRICAO", endereco completo, quadro societario,        |
|       socio majoritario).                                     |
|                                                               |
| 8. Compara valores novos com os valores atuais do negocio      |
|    (remove_empty_values + comparacao normalizada).             |
|    -> monta fields_changed / fields_unchanged.                 |
|                                                               |
| 9. Se fields_changed e dry_run=False:                          |
|    BitrixClient.update_deal(deal_id, {...})  [crm.deal.update] |
|    Se dry_run=True ou nao ha diferencas: nao chama update.      |
|                                                               |
| 10. Grava o resultado em cnpj_sync_log (SQLite), sempre —      |
|     inclusive em caso de erro.                                |
|                                                               |
| 11. Libera o lock do deal_id.                                  |
+-------------------------------------------------------------+
        |
        v
Resposta JSON: success, deal_id, cnpj, dry_run, fields_changed,
fields_unchanged, warnings, source
```

## Idempotencia

- Tabela `cnpj_sync_log` (SQLite, `app/db/models.py`) registra toda tentativa
  (running/success/error/dry_run), com CNPJ, campos alterados, avisos e hash da
  resposta da CNPJa.
- `force=false` (padrao): se ja existe um registro `success` para o mesmo
  `deal_id` + `cnpj` dentro de `SYNC_TTL_HOURS` (padrao 24h), a execucao retorna
  imediatamente sem nova consulta externa.
- `force=true`: ignora o cache acima e executa o fluxo completo novamente.
- Lock em memoria por `deal_id` (`DealLockRegistry`) impede duas execucoes
  simultaneas do mesmo negocio (HTTP 409 imediato na segunda chamada).

## dry_run

Com `dry_run=true`, todas as etapas 1-8 acontecem normalmente (incluindo a
consulta real a CNPJa e o calculo de diferencas), mas a etapa 9
(`crm.deal.update`) e pulada. O registro em `cnpj_sync_log` e gravado com
`status="dry_run"`, permitindo auditar o que teria sido alterado.

## Tratamento de erros e codigos HTTP

| Excecao | HTTP | Quando ocorre |
|---|---|---|
| `InvalidCnpjError` | 400 | CNPJ ausente, com tamanho errado ou digitos verificadores invalidos. |
| ausencia/erro de `X-Integration-Key` | 401 | Header ausente ou nao bate com `INTEGRATION_API_KEY` (comparacao em tempo constante). |
| `CnpjaNotFoundError` | 404 | CNPJ nao encontrado na base publica da CNPJa. |
| `ConcurrentSyncError` | 409 | Ja existe uma sincronizacao em andamento para o mesmo `deal_id`. |
| `CnpjaRateLimitError` | 429 | Limite de requisicoes da CNPJa atingido (local ou HTTP 429 remoto). |
| `BitrixApiError` / `CnpjaApiError` (outros) | 502 | Erro de transporte/protocolo do Bitrix ou da CNPJa. |
| `ConfigurationError` | 500 | Inconsistencia de configuracao (ex.: lista essencial nao encontrada nem no fallback). |
| qualquer outra excecao nao prevista | 500 | Nunca expõe stack trace ao cliente; logada internamente com `logger.exception`. |

## Logs

Todo log em nivel INFO usa `build_log_context` (`app/core/logging.py`), que inclui
`request_id`, `deal_id`, CNPJ **mascarado** (`12.***.***/****-34`), etapa, duracao
e resultado. A URL do webhook do Bitrix nunca aparece completa nos logs
(`mask_webhook_url`); o header `X-Integration-Key` e o corpo integral das
respostas externas nunca sao logados em INFO — apenas em DEBUG.
