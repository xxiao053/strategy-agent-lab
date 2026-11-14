# Development

[English](development.md) | [简体中文](../zh-CN/development.md)

## Repository layout

```text
lab/                 Backend, agent workflow and simulated account
web/                 Bilingual React workspace
scripts/             Local launch and market-data acquisition
tests/               Offline regression and optional integration tests
examples/cup-handle/ Reviewed configuration and derived result snapshot
examples/builder/    Genuine saved Builder projects and reviewed charts
docs/media/          Actual screenshots, captioned video and revision GIF
docs/en/             English guides
docs/zh-CN/          Matching Simplified Chinese guides
```

Runtime directories (`runs/`, `artifacts/`, `logs/`), virtual environments, web dependencies/builds and credentials are ignored. Local archives are kept outside the repository and are not required to build the software.

Docker distribution inputs are `Dockerfile`, `Dockerfile.worker`, `compose.yaml` and the exact runtime closure in `requirements-runtime.lock`; `.dockerignore` is an allowlist and excludes local data, credentials and dependencies. The frontend uses its frozen pnpm lock. See [Docker boundaries and acceptance status](docker-local.md). Ordinary tests skip engine acceptance; explicitly set `LAB_DOCKER_ACCEPTANCE=1` to run `tests/test_docker_engine_acceptance.py` only after starting the Linux engine and building the worker. These harmless tests use no model calls and must not be reported as passed when skipped.

## Test and build

```powershell
.\.venv\Scripts\python.exe -m pytest -q
pnpm --dir web test
pnpm --dir web build
```

Core tests use controlled fixtures and mocked network transports, not paid inference. Tests marked `market_data` require private frozen historical snapshots and are automatically skipped when those inputs are absent. To explicitly exercise the self-contained suite:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --without-market-data
```

Do not replace market-dependent checks with silently downloaded data. They pin source identity and are optional integration evidence, not a prerequisite to testing core behavior.

For frontend iteration:

```powershell
pnpm --dir web dev
```

The Vite development server proxies API requests to the local backend on port 8765.

## Continuous integration

The [CI workflow](../../.github/workflows/ci.yml) checks pushes and pull requests with read-only repository permissions and no model credentials. Its Ubuntu jobs run Python 3.13 self-contained backend tests against the locked runtime, plus Node.js 22 frontend tests and both local/static builds using the frozen pnpm lock. Private-market integrations and opt-in engine checks are not part of this automatic suite; a green CI badge does not establish live-provider compatibility or operating-system/Docker acceptance.

CI does not publish a website. The separate [Pages workflow](github-pages.md) remains manual-only. The README CI badge reflects the actual `main` workflow status, not a fixed passing label.

## Safe changes

Follow [Product direction](product-direction.md) when extending the product. The builder and execution have different responsibilities and permissions. Do not add a chat wrapper while retaining cup-only assumptions as the generic project interface, or add dependencies merely to cover a technology checklist. Preserve the existing demonstration while designing explicit method boundaries.

Preserve frozen run/configuration/data identities. New rules belong to new runs. Test sizing, date cutoffs, partial model outputs, request budgets and response reuse. Pausing or deleting research must not create free retries or erase consumed authorization.

Document implemented behavior, not future plans as if they already work. Update English/Chinese guides together. Adapter fixtures do not establish live provider compatibility.

## Sharing

Keep public source, tests, docs and reviewed examples separate from private runtime material. Before a public push, inspect the actual staged files for credentials, transcripts, databases and local paths. Confirm a software license and any necessary market-data permissions. Do not commit a private archive, even if it seems useful for debugging.

### Static showcase build and acceptance

GitHub Pages is the target for a read-only public showcase, not a hosted application backend. The separate static entry shares saved-project components with the local application and uses bundled data only. Both Builder examples and formal media are packaged; final release/content-rights acceptance and public deployment remain separate gates. The original execution example is separately labeled and does not establish new builder output.

Build a local preview without publication configuration:

```powershell
pnpm --dir web build:showcase-preview
```

Serve `web/dist-showcase-preview/` with a static HTTP server. Relative assets and hash links support project subpaths and refresh without a routing backend. Both modes use **My projects** and the conversation/inspector workbench. Local native projects take precedence over portable records with the same explicit source identity; unrelated projects with matching titles remain separate. Static projects are read-only and make no model calls. The preview omits the GitHub link when no repository has been configured; its local-run guide remains available.

The release command `pnpm --dir web build:showcase` requires `VITE_SHOWCASE_REPOSITORY` to contain the approved HTTPS GitHub repository URL and a reviewed full builder example at `examples/builder/cup-complete/project.json`. It writes `web/dist-showcase/` and does not upload anything. A build is not publication approval. Keep bundled examples and image filenames explicitly reviewed, and update the narrow Docker input list and web-stage copies when adding them.

Before publishing a showcase build:

The included **Review or publish static showcase** Actions workflow is manual-only. Its default builds/tests and uploads a review artifact, not a website. After the release checks below and owner approval, configure repository Pages to use GitHub Actions and dispatch with **publish** enabled. Only that deployment job receives Pages-write authority. Source links derive from the actual repository; no model credentials are used. The [public workbench](https://xxiao053.github.io/strategy-agent-lab/) is deployed through this workflow; subsequent updates still require manual dispatch. Its file uses JSON, a strict YAML subset.

- Load reviewed, redistributable examples without credentials, a runtime database or a running local backend. Test in a fresh browser with no saved application state.
- Verify navigation, direct links, refresh, assets and media under the project's Pages path. Check that neither local API endpoints nor model providers receive requests.
- Identify saved records as demonstrations; omit credential forms and unavailable live actions. Check that source and local-run links lead to valid destinations.
- Review the complete static artifact, including bundled example data, JavaScript, source maps and media, for private information and distribution rights. Static assets are publicly downloadable, even when not displayed by the UI.
- Keep deployment behind release review and explicit publication approval. Preparing a build or workflow does not authorize making it public.

## Security and release gates

Local distribution removes a shared hosted account from the design, not prompt-injection or host-security risks. Imported documents, copied notes, reference code and tool results may contain hostile instructions. Prompt wording and structured responses are supporting defenses; permission, filesystem, network and spend boundaries must be enforced outside the model. An owner deliberately modifying their own source is different from a normal installation being manipulated by untrusted material.

Design controls alongside features, then perform a scoped release security review covering:

- Credential exposure through API responses, validation errors, logs, exports, environment inheritance, image layers and build caches.
- Chat/material/tool-result injection, unauthorized method changes, forged validation evidence and access to future historical information.
- File traversal, links, uploads/parsers, script/HTML rendering, local web origins/hosts and unauthorized requests to the local service.
- Native/container escape boundaries, mounts, network/broker access, Docker socket exposure, dependencies and runtime provenance.
- Cost reservation, unknown billed outcomes, request/loop/resource limits, interrupted runs, cleanup and recovery.

Use harmless canaries and offline fixtures where possible; live security probes require explicit scope and budget. Report tested versions/environments, reproducible findings, fixes/retests, untested areas and residual risk. Existing unit tests or a clean secret-pattern scan do not constitute a complete security audit or guarantee zero risk.

Review the actual release contents separately from runtime security. Include product source, useful automated tests, current bilingual docs and sanitized, redistributable examples/media. Exclude private plans/archives, superseded documents, obsolete code, temporary scripts, internal development narratives (including comments), parameter searches, discarded runs, troubleshooting records, raw provider transcripts, databases, credentials and unlicensed source data. Genuine, reviewed product-level builder conversations may belong in an example; conversations about developing the platform do not. Check dependencies before archiving obsolete material outside the repository; do not remove useful tests, license notices, user-owned projects or evidence of actual product limitations for presentation. Inspect staged files, all history being published, archives, static-site artifacts, media, Docker build context and image layers; `.gitignore` does not protect every export path. If a real credential was published, revoke/rotate it rather than merely deleting its current file.

Original software and documentation use [MIT](../../LICENSE); preserve [third-party notices](../../THIRD_PARTY_NOTICES.txt). Both frontend modes emit these notices and the bilingual [data notice](../../DATA_NOTICE.md); Docker retains them at the application root and in the frontend output. When changing dependencies, update their exact notices and verify packaged license files, not just metadata labels. Data/media redistribution rights remain separate from software licensing. See [Pages review and publishing](github-pages.md). No push, public upload or image publication follows automatically from finishing a review. Keep detailed private findings outside the public repository while publishing accurate user-facing security limitations.
