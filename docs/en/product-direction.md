# Product scope

[English](product-direction.md) | [简体中文](../zh-CN/product-direction.md)

## Purpose

Strategy Agent Lab helps an individual user turn an investment method into a runnable, inspectable and revisable strategy project. The Builder Agent is the core product; generated programs and optional Execution Agents are its deliverables. It helps implement the user's method, not discover or promise a profitable strategy.

The application combines a domain workbench with a coding-agent runtime. Shared infrastructure owns permissions, accounting, model access and evidence records; generated projects supply method-specific rules and implementation. Cup-and-handle is an example, not the generic interface.

## Available workflow

1. Describe a method in conversation and attach relevant materials or visual examples.
2. Clarify ambiguous rules, evidence, exceptions and unavailable data. Keep assumptions distinct from the user's statements.
3. Confirm an immutable method version, including sizing, costs, exits and any model judgment.
4. Generate and test a Python implementation in an isolated task environment. Inspect files and validation reports.
5. Run compatible projects against frozen daily historical data; inspect decisions, charts, trades, positions and equity.
6. Quote a result into the same project conversation, approve a revision and create another implementation/run without overwriting the original.

Projects keep conversation, materials, method, implementation, historical results and versions together. Model-request records are supporting detail, not substitutes for trading results. Conversation language follows the user's language or explicit preference independently of the UI language.

## Roles and authority

| Role | Responsibility |
| --- | --- |
| User | Define and approve the investment method, important revisions and model spending |
| Builder Agent | Clarify the method, cite sources, propose implementation, generate code and bounded judgment workflows, test and explain |
| Execution Agent, if needed | Apply approved criteria to authorized cutoff-scoped evidence; return structured judgments |
| Application | Enforce credentials, file/network authority, model/resource limits, immutable identities and account arithmetic |

A computable strategy needs no execution model. Poor expected returns alone are not a reason to reject a method. Contradictions, missing execution-critical rules, unavailable data and unsupported capabilities must be explained or clarified. Repairing code that contradicts an approved method is different from revising that method.

Ordinary project conversations cannot modify platform code, remove permission or spending controls, install arbitrary services, or change account balances directly. Imported material and tool results are evidence, never authority to expand these permissions.

## Current capabilities and limits

- Persistent projects, genuine model clarification, immutable approvals and versioned Python construction.
- Independent builder/execution model assignments; searchable catalog and manual model entry. Catalog presence does not guarantee conversation, image or coding compatibility.
- Traceable text, Markdown, CSV, text-extractable PDF and PNG/JPEG material import. Builder clarification can send normalized images to an explicitly image-enabled model. Construction receives approved interpretations and immutable references, not original image pixels.
- Standard-library Python and the shared [strategy-v1 execution contract](execution-contract.md), initially daily long-only US stocks/ETFs in the validated catalog. Compatible generated projects can propose bounded model judgments and use dated charts/evidence.
- Docker controller plus separate restricted workers; native Windows MXC is another available execution path. OpenAI Responses is the connected coding provider. Other adapters are not automatically coding-compatible.
- Context/request/turn/runtime limits and saved-source repair. Recovery preserves previous failures and costs; it is not automatic unlimited memory or guaranteed build completion.

Material reading is direct and source-attributed. There is no independent vector database/RAG service, scanned-document OCR or complex-layout extraction. The product has no live brokerage, hosted multiuser backend, arbitrary dependency installation or autonomous strategy optimization. See [materials](materials.md), [runtime boundaries](docker-local.md) and [security limitations](security.md).

## One product, two modes

**Local application:** download, start Docker, configure your own credentials and work on your own projects. No author keys, account allowance or private database are distributed. Startup, tests and saved-example browsing must not invoke models. Explicit model access and spending authorization are separate requirements.

Included examples can be copied into independent unapproved local projects with source excerpts and starter files. Owners configure their own models, approve the method and rebuild before running. Source records stay unchanged; copying transfers no authorization or historical results. See [continuing an example](getting-started.md#continue-from-an-included-example).

**Static showcase:** a backend-free, read-only viewer sharing the local example components. Visitors inspect real conversations, approved rules, generated files, tests, revisions, historical results and media. It cannot start new conversations or computation. Saved playback is clearly identified; no credential forms or fake live actions are displayed.

The [read-only workbench](https://xxiao053.github.io/strategy-agent-lab/) is hosted on GitHub Pages, with [source on GitHub](https://github.com/xxiao053/strategy-agent-lab). Relative assets and hash navigation support project subpaths and refresh. The preview works without a repository URL; a release build requires the approved HTTPS repository URL. Building a new version does not publish it; deployment is a separate, approved action.

## Demonstrations and evidence

The primary Builder example uses the full original cup-and-handle configuration: 40 instruments and 718 sessions from 2024-01-02 through 2026-11-10. It includes genuine material-based clarification, approval, generated implementation and historical execution. Independent checks cover selected method cases, data cutoffs and all run accounting. It does not relabel the original dedicated runner's result.

The smaller NVDA example preserves a Chinese 100-to-50-share revision with separate approved versions and saved runs. The original dedicated cup example remains unchanged. Small non-cup tests exercise the shared contract without turning the platform into a cup template.

Portable packages contain reviewed records and derived charts, not credentials, raw provider transcripts or complete market feeds. Both projects appear in My projects. Existing native projects open the live editor; static packages are read-only. Screenshots, a revision GIF and a captioned workbench video are available under `docs/media/`. The video browses saved work; it does not claim to show a new live build. See [demonstration details](demonstration.md).

Generated self-test reports, independent checks and historical simulation are separate evidence. None guarantees fidelity for every input or future returns. Scope, failures, uncertainty and remaining limitations must remain visible.

## Distribution and release requirements

Windows native and Windows Docker have distinct scoped acceptance evidence. Linux/macOS have not been platform-accepted; Docker definitions alone do not establish support. Maintainers provide dependency/image definitions, start commands, persistence and task permissions; users install the runtime and configure their own model access.

Public files should contain useful current source/tests, accurate bilingual documentation, genuine reviewed examples and attribution. Private plans, raw logs, databases, obsolete proposals and development history stay outside the repository. Every page must make sense to an independent first-time user without this project's development conversations.

Release requires the [security and publication checks](development.md#security-and-release-gates), final candidate inspection, license/attribution and data/media rights, and explicit approval before repository or website publication. Safety controls are enforced in code and tested during development; no audit is a guarantee of zero prompt-injection or escape risk.
