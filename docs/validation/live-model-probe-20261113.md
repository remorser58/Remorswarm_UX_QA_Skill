# Live model probe — 2026-11-13

This is a **real model transport and synthetic-session probe**, not product UX QA. The 32 sessions used 32 authored preference profiles and isolated three-turn chat histories over one fictional mobile checkout scenario. No saved research persona library, browser, screenshot, actual product, real account or human participant was involved.

## Stages

| Target sessions | New sessions | Model turns | Input tokens | Output tokens | Wall time | Fallback sessions |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 1 | 3 | 2184 | 692 | 12.823s | 0 |
| 5 | 4 | 12 | 8916 | 2885 | 37.810s | 0 |
| 21 | 16 | 48 | 35240 | 11613 | 130.271s | 1 |
| 32 | 11 | 33 | 24493 | 6545 | 90.993s | 0 |

## Provider totals

| Route | Attempts | Transport-valid responses | Failures | 429 | Input tokens | Output tokens | Cost record |
|---|---:|---:|---:|---:|---:|---:|---|
| inferhub/combo/deepseek-4-1-flash | 2 | 1 | 1 | 0 | 324 | 700 | Actual cost unavailable; conservative estimate upper bound USD 0.0002343 |
| TOKENMAXX/deepseek-v4.1-flash-free | 97 | 96 | 1 | 0 | 71302 | 21803 | Free route: $0 |


The InferHub estimate is not an invoice: the OpenCodex response did not expose a provider charge. It applies 50% of DeepSeek V4.1 Flash published rates ($0.15 input / $0.60 output per million tokens), consistent with InferHub published maximum publisher ask of 50% of upstream official rates. Actual combo-member pricing and settlement were not independently verified.

## Interpretation

- TOKENMAXX was the primary route. One session used the confirmed InferHub DeepSeek combo as fallback after a primary response failed the JSON quality gate. The InferHub response itself needed one retry after an invalid protocol response before returning a valid result.
- A separate TOKENMAXX HTTP 502 was retried and recovered; no 429 was observed.
- No HTTP 429 was observed in these live calls. The separate offline router regression test confirms 429 backoff and fallback behavior; it is not evidence of provider throughput.
- The InferHub Haiku route was not configured: no Haiku model ID appeared in the Mac mini OpenCodex /v1/models catalog. The official public catalog does list Haiku aliases, but that does not make them available through this local gateway.
- The test establishes local gateway routing, response parsing, isolated conversation state, usage capture and fallback behavior only. It does not establish that a synthetic persona behaves like a real user or that the product UX has been tested.

Raw stage receipts and per-request usage ledger remain in the private worktree .ux-loop/live-model-probe-20261113-r2/ and .ux-loop/live-model-probe-20261113-r3/; no credentials or prompt secrets are included in the report.
