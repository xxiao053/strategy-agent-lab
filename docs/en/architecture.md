# Architecture

[English](architecture.md) | [简体中文](../zh-CN/architecture.md)

## Target product and current scope

The product is a Builder Agent that turns user methods into executable strategy projects; an Execution Agent is an optional project component. Generic construction connects to the shared generated-project historical runner. The original cup example remains a separate, unchanged execution path. See [Product direction](product-direction.md).

The original cup schema, assessment fields, prompts, tools and runner remain method-specific. Shared execution uses the separate strategy-v1 contract. Fixed cup regions, three rubric items and a numeric-first pipeline are not requirements for other methods.

## Project construction

`workspace_store` persists projects, conversations, drafts, approvals, request costs and build records separately from frozen historical research. `workspace_agent` uses a generic method schema; source message IDs accompany new material. Approvals save immutable method versions.

`example_copy` accepts only fixed shipped example IDs and a selected method version. It validates source hashes, bounded files, portable paths and citations before atomically creating an unapproved draft. Reviewed excerpts receive fresh project-local IDs and canonical hashes. Copies inherit no credentials, role assignments, approvals, receipts, runs or execution seals. Starter source is an untrusted input to normal construction, never imported by the host; source provenance links to the unchanged example.

`materials` imports project-scoped private text/Markdown, CSV, text-extractable PDF and still PNG/JPEG examples through the selected isolated boundary. Originals and parsed previews have immutable IDs and hashes under `LAB_DATA_ROOT`; selected line/page/record/image references are bounded, preserved through revisions and frozen in approved methods. Authorized clarification can send normalized pixels to an explicitly image-enabled model. Construction receives the approved interpretation and immutable references, not original image pixels. Both `build_runtime` and `sdk_builder` stage and integrity-check explicitly untrusted `MATERIAL-REFERENCES.json` before independent verification. The coding runtime never receives original material paths or store access. See [material workflow and limits](materials.md).

`connections` manages explicit user-selected provider/model connections. Session credentials stay in memory; optional Windows persistence uses DPAPI. Catalog checks request metadata only and do not establish inference access.

Projects expose `model_roles: {builder: connection_id|null, execution: connection_id|null}`; legacy projects read as explicit unset roles. `POST /api/workspace/projects/{pid}/models` atomically validates both saved connections and rejects active-task changes. Conversation and construction resolve the builder; optional historical judgments resolve only execution. Requests snapshot their role/connection/model. Legacy direct conversation/build requests remain supported only when the builder is unset. Missing bindings never fall back. `POST /api/workspace/connections/catalog` accepts provider plus explicit key/environment consent without model/name/prices, performs bounded metadata reads and creates no connection. Catalog, structured conversation and validated construction observations are separate.

`build_runtime` invokes the installed Codex CLI with an isolated runtime home, no inherited login, no ancestor instructions, denied outside reads/writes and disabled command network. Runtime binaries have narrowly scoped read access. A non-secret canary probe must pass before inference. A host-side relay holds the real API key, reserves the shared project budget before every request and persists response events. It limits request size, output tokens and request count; unknown outcomes are not automatically retried. Process limits bound runtime duration, captured output and process-tree memory; children are cleaned up.

Each build has a new workspace tied to one approved version. Code, test outputs and synthetic results are retained. Host-selected test/demo commands and independent strategy-v1 input/output checks run in isolation; method/contract changes and reports of zero executed tests are rejected. Generated test code can misreport its own success, so its output is explicitly labeled a self-test report, not independent verification. Independent method cases, source integrity, cutoff and accounting checks are separate evidence; neither establishes correctness for all inputs. Construction uses either Windows MXC/Codex CLI or Docker workers/OpenAI Agents SDK, with OpenAI Responses and standard-library Python. Completed contract-aware artifacts receive a frozen execution hash for historical runs.

Eligible saved source seeds later construction instead of requiring complete regeneration. Same-version failed artifacts are independently verified first; if already complete and passing, a new verification-only successful record is created without inference. Otherwise model-assisted repair remains subject to separate authorization and limits. Previous failures and costs remain unchanged. Native construction supports bounded local history compaction; Docker saved-source recovery does not include automatic in-session compaction. Either path can still reach request, time or budget limits. See [construction limits and recovery](docker-local.md).

Generated files currently live under `runs/builds/<project-id>/<build-id>/project/`, beside a separate per-build runtime directory. These local outputs are ignored by Git; only reviewed exports become public examples. Saving locally does not imply that authorized model requests contain no project context.

## Shared execution contract

`execution_contract` validates the [strategy-v1 manifest and decision envelope](execution-contract.md), including history, code/model responsibilities, optional criteria/tools/uncertainty, integer-share proposals and bounded JSON strategy state. `project_evaluator` uses the selected MXC or Docker boundary with fresh cutoff-scoped inputs per date and never imports generated code in the host. Isolation failure never falls back to host execution. `project_account` owns decimal-cent cash, fees, long-only positions and next-open fills without invented stop/target or final-liquidation rules.

Historical input must be bounded to information available at the decision time, including documents as well as prices. Strategy code and tools cannot read the full future dataset. Decisions go through validated interfaces to the account simulator rather than mutating balances or manufacturing fills. A legitimate no-trade judgment, insufficient evidence, missing data and infrastructure failure must remain different recorded outcomes.

`project_runs` freezes and hashes approved method, artifacts, manifest, validated local market snapshot, model parameters and assumptions. Its dedicated SQLite table separates bounded detailed results from summary/status polling; restart marks interrupted, never auto-resumes. `project_judgment` provides up to one read-only evidence-tool round and one final answer under the shared project budget, with durable request IDs/receipts. `ProjectRuns` presents configuration, progress, equity, total return, maximum daily-close drawdown, fills, open positions and evidence and can quote a decision into the same conversation. Local and packaged results share the same performance calculation: return uses frozen initial cash, and drawdown uses the full recorded daily-close equity path with initial cash included as the starting peak. These are not annualized return or intraday drawdown. Revisions create new versions/runs. Initial data remains the validated US stock/ETF catalog, not arbitrary ingestion; optional live/model/runtime acceptance is distinct from offline contract tests.

Methods may optionally declare a managed risk/account policy and ranked fixed entry candidates. `project_managed` adapts the existing account arithmetic without calling its strategy-specific screening or historical runner; absent this policy, fixed-share behavior is unchanged. `project_assessments` validates named candidate rubrics, optionally reviews every non-pass result, and selects the first ranked final pass without changing geometry. Calculation history and model-visible history can differ explicitly. Larger runs retain lossless cutoff references into their frozen market snapshot rather than duplicating every rolling window. These contracts support up to 100 catalog symbols and 756 sessions; they do not establish that a particular generated implementation faithfully follows its approved method.

## Docker backend and local distribution

The explicit Docker backend uses OpenAI Agents SDK 0.24.0 in the trusted controller with bounded shell/filesystem tools in hardened, networkless worker containers. Historical decisions use copied, per-task read-only volumes, not controller bind paths. `docker_policy`, `docker_runtime`, `sdk_budget` and `sdk_builder` separate policy, lifecycle, request accounting and SDK integration. See [Docker local distribution](docker-local.md) for launch instructions, trust boundaries, quotas and the platform verification matrix. Real Docker construction and historical execution have been exercised on Windows; native Windows launch still defaults to MXC, while the maintained Compose launch selects Docker.

Isolated execution is a replaceable backend. Docker is the cross-platform distribution target and has scoped Windows acceptance; MXC remains the native Windows default. Linux/macOS host acceptance is separate. Docker support requires more than containerizing the web server: coding, independent tests and strategy execution must preserve the same boundaries.

Maintainers supply pinned runtime dependencies, image/build definitions, launch configuration, persistence mapping, resource limits and upgrade checks. Users install and start a compatible Docker runtime and supply their own model credentials; they should not design container permissions themselves. Persist project outputs on the host or in explicitly managed storage independent of disposable containers. Mount only task-specific writable content and necessary read-only resources, not the entire host or checkout.

Generated workloads receive no host provider keys, personal login, privileged container mode or Docker control socket. A controlled broker mediates permitted external requests and charges them against authorization. Validate outside-path access, network restrictions, resource exhaustion, process cleanup and restart behavior. Cross-platform secret storage and operating-system/CPU compatibility require separate verification; a Dockerfile alone does not establish support. Installation or enabling system virtualization is not authorized by model-spend approval.

## Included cup execution workflow

**Approved method → frozen data → numeric candidates → account eligibility → agent judgment → validated signal → simulated portfolio → inspection.**

| Component | Responsibility |
| --- | --- |
| User | Supply and approve the method, judgment rubric and execution parameters |
| Strategy engine | Indicators, numeric conditions, stable candidate geometry and identity |
| Agent | Apply the approved rubric to specified candidates; request bounded evidence tools |
| Account engine | Cash, position sizing, orders, fills, costs and exits |
| Run controller | Sequence work, enforce budgets, validate outputs, persist and recover |

This historical runner accepts the configurable cup-with-handle method. Builder-generated projects use the separate construction path above; they are not silently mapped onto this runner.

## Bounded agent execution

Each opportunity provides fixed candidate IDs, numeric facts, cutoff-limited bars/charts and a compact reference pack. The model assesses cup, handle and coherence, returning pass, fail or insufficient evidence for every candidate.

Tools can inspect a permitted data interval, calculate candidate metrics or generate a local detail chart. They cannot access later bars, change anchors, modify account state or search the web. Each stage permits one tool roundtrip and one output repair within a three-request ceiling. Conditional review handles non-pass primary assessments under the same run budget.

Required candidate keys, rubric aggregation, evidence dates and geometry are validated locally. A technical failure pauses the run; it is not converted into a strategy rejection.

## Data and execution

Snapshots are validated for identity, checksums, ordered trading sessions and OHLCV consistency. Historical decisions only receive information up to their cutoff. This input boundary does not remove knowledge potentially memorized during model training.

Code screens numeric candidates and checks whether any can be traded before requesting new inference. Held positions, pending orders and reserved cash count. Model approval cannot bypass position, cash or risk limits.

Signals use the close; orders fill no earlier than the next session's open, with configured costs and gap rules. Exit decisions belong to code, not the LLM. The account supports fixed stops/targets and configured lack-of-progress/trailing rules. It does not use an unconditional holding-age sale.

## Persistence and recovery

SQLite stores frozen configurations, data identities, account checkpoints and request receipts. Successful provider responses are saved before parsing. Resumption verifies exact request identity and reuses known responses; unknown billing outcomes are not automatically retried.

Incomplete-output recovery is explicit, versioned and bounded. Deleting a research record cannot reset its already-consumed shared budget; aggregate committed spend remains. Selecting a demonstration requires a completed model run, not a baseline comparison.

## Implementation

- Python, FastAPI, Pydantic, SQLite and a single local worker.
- React, TypeScript and Vite for the bilingual workspace.
- Backend provider adapters; no browser-side credentials.
- Direct, source-attributed method references; no vector database or RAG dependency.
- No unrestricted multi-agent voting, distributed queue, broker integration or multiuser authentication.

The local server rejects nonlocal hosts and cross-origin requests. These protections are not a substitute for the separate security design needed for public hosting.

Provider JSON responses are capped at 32 MiB before parsing; native construction streams at 64 MiB total and 8 MiB per event line. Remote compression is not accepted. Elapsed transfer limits are checked between received chunks (240 seconds), with a separate 120-second socket-idle bound; an outstanding blocking read can extend past the elapsed threshold up to that idle bound. Exceeding a limit retains an unknown-outcome reservation and never silently retries. Child-process input and output flow concurrently so a full input pipe cannot bypass its supervisor's timeout.

The SDK asynchronous receive path wraps send/read in a 240-second cancellation deadline. Catalog and market-download paths also reject compression before consumption, buffer incrementally, and enforce 1 MB / 4 MB body limits and 30-second between-chunk elapsed checks, with separate 20 / 10-second idle timeouts. These metadata paths are not inference and create no model charge.
