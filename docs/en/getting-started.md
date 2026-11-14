# Getting started

[English](getting-started.md) | [简体中文](../zh-CN/getting-started.md)

The home page is the Builder workbench. **My projects** lists your local projects and the bundled full-cup and NVDA examples. Browse the examples without credentials, or create your own project and connect a model.

## Install and launch

Prefer the supplied [Docker distribution](docker-local.md) when evaluating the portable package: it supplies dependencies and isolated task images. Read its explicit verification matrix first. The native Windows path below remains MXC by default.

Use Python 3.11+, Node.js 20.19+ or 22.12+, and pnpm. In PowerShell, from the repository root:

```powershell
.\bootstrap.ps1
.\start.ps1
```

The bootstrap creates a Python environment, installs dependencies and builds the web app. The launcher serves only [127.0.0.1:8765](http://127.0.0.1:8765) in the background. Neither command calls a model. Use the language selector for English or Chinese.

A fresh checkout includes the full-cup Builder project and NVDA revision as reviewed portable records, with conversations, methods, generated files, tests and historical results. Existing native projects open in the real editor; bundled records are read-only. The original cup execution [result snapshot](../../examples/cup-handle/result.json) has its own sidebar entrance. None depends on the author's database.

## Continue from an included example

In the local application, open a bundled project, choose a **Method version**, then **Create editable copy**. This creates your own unapproved draft, copied source excerpts and starter code. The original conversation, approvals, tests and historical results remain in the source project, linked from the copy; they are not new results belonging to your copy.

Configure your own model roles, review and approve the draft, then **Build and validate**. The builder uses the starter files as untrusted editing inputs and validates the resulting implementation against your approved method. To run history, prepare your own market data and authorize any model judgments separately. Copying itself makes no model calls and imports no credentials, spending approval or successful build status. Excerpts do not recreate original image files. The static showcase is read-only and has no copy action.

## Build your own project

1. Open **Model settings**. Choose a provider and enter your API key, then **Fetch model catalog**, search and select a model. Manual **Model ID** entry also works when the catalog fails. Name the connection, enter current token prices and save. Optional Windows-protected storage survives backend restarts; session storage does not.
2. **Check connection** rechecks a saved connection's catalog without inference. Listing is not a guarantee of model access or task quality; choose a model that supports the input and construction workflow you need.
3. Choose **New project**. Start with notes or an incomplete method. The assistant asks about important gaps and maintains the method draft.
4. Select the project's **Builder model** and, if useful, an optional **Execution model**, then choose **Save model roles**. Unsaved changes block model tasks and require fresh spending approval after saving. Code-only methods need no execution model. Set the cumulative budget and authorize calls. Review the draft and **Approve current method** when critical questions are resolved.
5. On a supported construction installation, select **Build and validate**. Inspect generated files, independently rerun tests and explicitly synthetic output under **Implementation & validation**. **Model calls** retains requests and costs, not trading results. Downloads contain project files, not credentials.
6. Describe a correction, approve the new draft and build that version. Earlier versions and outputs stay unchanged.

Native Windows construction requires Windows 11 with [MXC support](https://learn.chatgpt.com/docs/windows/windows-sandbox#mxc-compatibility), an installed [Codex CLI](https://learn.chatgpt.com/docs/codex-cli), and an OpenAI Responses model. The maintained Docker launch instead uses separate workers and the OpenAI Agents SDK; see [Docker setup](docker-local.md). Neither path borrows a personal Codex login: it uses the selected API connection and stops before coding inference if isolation is unavailable. Generated code uses the Python standard library. Construction checks use synthetic inputs; historical simulation is a separate explicit step below.

## Run a generated project

Before building, use the project's **Materials** tab to import notes or numeric/rubric references, inspect literal source locations and attach selected text to chat. Import/preview are offline; sending a message requires separate model authorization. Source text is frozen at method approval and supplied to both coding backends. See [materials and limits](materials.md).

After a successful contract-aware build, open **Runs & results**. Choose the build, supported symbols, covered trading sessions, initial cash and per-side fees. Missing or insufficient local market data blocks the run with a readiness error; it is never replaced with synthetic prices. Older builds without `execution.json` and a verified seal must be rebuilt, but remain viewable.

For fresh local data, select **Prepare data** in this same panel. This explicitly fetches the selected scope and required warmup from the fixed market provider, shows progress and preserves existing snapshots; it never calls a model. Session-only connections can be repaired after restart using **Re-enter key**, preserving project role assignments.

Only methods with model judgments require a saved execution connection and the run-specific spending checkbox. It shares the project budget with conversation/construction. Pure-code runs do not call providers. Inspect saved curves, fills, positions, all input symbols, judgment criteria and tool results. **Quote decision in conversation** inserts a validated evidence reference without sending a message; the selected inputs/fills/state/model evidence and code excerpts will accompany your separately authorized builder request, with explicit context omissions. The attachment can be removed. Review your correction and authorize the builder separately. Cancel stops future work without erasing evidence or cost. Restart marks interrupted; there is no automatic spend/resume. See [Execution contract and limits](execution-contract.md).

## Optional: included cup historical research

Open the original cup execution reference from the sidebar footer to use the existing cup runner. Its model configuration and market data are separate from Builder projects.

### Prepare market data

The initial implementation uses frozen Yahoo daily OHLCV snapshots. Fetch data before creating a run:

```powershell
.\.venv\Scripts\python.exe -m scripts.freeze_market --config examples/cup-handle/config.json
```

This downloads the example's instruments and interval, including strategy warmup. It makes network requests to the data provider, but no paid model calls. Downloads are checksummed, validated and kept under ignored `artifacts/`; existing source files are not overwritten. Provider revisions may prevent exact reproduction of an earlier snapshot.

For another interval:

```powershell
.\.venv\Scripts\python.exe -m scripts.freeze_market --start 2024-01-02 --end 2025-12-31 --symbols AAPL MSFT QQQ
```

Then select matching covered trading dates/instruments in the workspace. Do not assume an open-source client license grants rights to redistribute the market feed.

## Configure a model

Create a local `.env` from `.env.example` only if you do not already have one. Set the appropriate backend environment variable, then restart the local server. Do not put credentials in the method description, browser storage or committed files.

See [Models and budgets](models.md). A provider being configured does not prove a particular model supports images or tools.

## Run and inspect

1. Open **New research** and edit the supported method, numeric conditions and judgment criteria.
2. Confirm the method, instruments, dates, account and execution rules.
3. Run the opportunity preflight. Candidates are not guaranteed trades.
4. Select model research, confirm capability/pricing information and explicitly approve its cost limit. A program-only run is available for local engineering checks, but is not the product demonstration.
5. Inspect progress, decisions, trades, positions and model records.

The account is shared across instruments. An accepted judgment may still not fill because of price gaps or account constraints. At the end of the interval, open positions are marked to market, not forcibly closed.

## Pause and replay

Pause takes effect at a safe boundary. Successful responses are persisted before interpretation, so resuming can reuse them. Unknown transport outcomes require explicit acknowledgment because the provider may already have billed them. Replay uses saved responses with matching versions; it does not guarantee identical answers from a new model call.
