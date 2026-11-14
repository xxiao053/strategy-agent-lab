# Models and budgets

[English](models.md) | [简体中文](../zh-CN/models.md)

Model credentials belong to the user and are read only by the local backend.

In the Builder, use **Model settings** to choose a provider, enter your API key (or explicitly select its environment key), and **Fetch model catalog** before naming or saving a connection. Search and select a listed model, or enter a **Model ID** manually, then provide a name and current prices and save. Keys are never returned by the settings API or stored in browser persistence. Session-only keys disappear when the server restarts; Windows DPAPI persistence is optional. Catalog checks do not perform inference or establish full model compatibility.

Method conversations use the provider adapters below. Code construction uses OpenAI Responses through native Codex CLI or Docker-backed OpenAI Agents SDK; Claude/Gemini/domestic coding backends are not yet connected. Luna is a demonstration choice, not a required model. Select another supported model and its actual rates; access and task quality still need verification.

Construction requests use a shared per-project budget, capped output/context and up to 50 requests per Docker build or 16 per native build. A 1.5× safety factor applies only to pre-call reservations, not completed usage pricing. Unknown responses retain their reservation. Generated commands receive no provider key, no inherited Codex login, and no network access.

| Provider | Environment variable | Verification |
| --- | --- | --- |
| OpenAI | OPENAI_API_KEY | Luna live-tested |
| Anthropic | ANTHROPIC_API_KEY | Offline adapter tests |
| Google Gemini | GEMINI_API_KEY | Offline adapter tests |
| DeepSeek | DEEPSEEK_API_KEY | Offline adapter tests |
| Qwen | DASHSCOPE_API_KEY | Offline adapter tests |
| Kimi | MOONSHOT_API_KEY | Offline adapter tests |
| GLM | ZHIPU_API_KEY | Offline adapter tests |
| Doubao | ARK_API_KEY | Offline adapter tests |

The demonstration uses `gpt-6-luna` with low reasoning. Adapter availability is not a promise that every model supports the same image, structured-output and tool features. In particular, the current DeepSeek adapter rejects image requests; select text-only input or an appropriate vision model. There is no silent image omission or automatic provider fallback.

Qwen can use a supported regional/workspace endpoint via `QWEN_BASE_URL`. Custom endpoints are restricted to approved provider hosts.

## Model selection and project roles

The setup flow is **provider → credentials → fetch catalog → search/select a model → save**. Manual model entry remains available when a catalog fails, is unsupported, or does not list the desired model. This does not grant permission to contact arbitrary URLs. Changing provider or credentials clears the catalog, and outdated responses cannot populate another credential context. Reading a catalog is separate from a paid capability test.

Each project saves a **Builder model** for both clarification and construction and an optional **Execution model**. Edit both selections, then choose **Save model roles** to save the pair together; this also lets you replace two unavailable connections in one operation. Unsaved edits revoke spending approval and block model calls or construction until saved and explicitly authorized again. They may use the same connection or different connections. Leave Execution unset for a code-only method. Generated-project historical judgments use only the saved execution role, with separate run authorization and the same cumulative project budget. The cup example retains its separate legacy settings. See the [bounded execution contract](execution-contract.md).

Switching projects restores their roles and clears spending approval. Old projects start with both roles explicitly unset; select their Builder model before using the UI for live tasks. Removing a connection leaves a visible missing binding, not a fallback. Reconfigure credentials or select a configured connection. Roles cannot change while a project has an active task. New conversation requests, construction requests and build records snapshot the builder role and connection; older records and costs remain unchanged. The cumulative project budget remains authoritative.

Catalog results help select a model; they do not establish image understanding, structured-output compatibility or coding quality. Model settings expose configuration and actionable access errors, not internal acceptance badges. Construction requires a supported OpenAI/native or Docker runtime; inspect each project's actual files, test reports and run evidence rather than treating a connection as a correctness certificate.

## Before a paid run

Confirm the actual model ID, selected input capabilities, input/output USD rates and spending limit. A new configuration never inherits paid authorization from a demonstration. Keys stay in environment variables or an ignored local `.env`, not prompts or browser storage.

## Cost accounting

A candidate opportunity is not an API request. Tool followups, conditional reviews and repairs can produce several requests. All count toward request and dollar limits, including failed calls with reported usage.

Requests reserve budget before dispatch. Usage records track input/output/cached/reasoning details where reported; reasoning already included in output is not counted twice. Shared authorization includes previously consumed or conservatively reserved spend even when old research records are removed.

The project workbench displays separate categories:

- **Budget occupied:** usage-priced amounts plus outstanding reservations and retained legacy budget records. This is authorization accounting, not paid spend.
- **Usage-priced amount:** reported token counts multiplied by the saved configured prices, with applicable supported cache/long-context rates and no safety multiplier. A configured price is not confirmation of a provider charge.
- **Provider bill:** not connected. No invoice amount is available; this does not mean no charge occurred.

New requests retain separate reservation, usage-priced amount and price snapshots. Missing usage or cache prices retain the reservation. Legacy records keep their original values and are excluded from the new usage-priced total; no retrospective repricing is performed. The original cup runner's separate historical estimate is not an invoice either. See [pricing details](materials.md). Unknown outcomes retain their reservations until explicitly handled. Stop with a visible diagnostic when limits are reached; do not retry indefinitely.

## Privacy

Never commit a real `.env`, credential file, run database or raw request archive. The public example contains derived results and selected assessments, not provider response identifiers or complete transcripts. Review any new export before sharing.
