# Security and limitations

[English](security.md) | [简体中文](../zh-CN/security.md)

## Intended environment

Run a trusted copy locally as a single user. The application is not designed for public internet exposure, shared untrusted users or live brokerage. The static showcase is a separate read-only artifact with no inference backend.

The Docker controller holds the Docker socket, which grants authority over the Docker host. It is trusted application code, not a security boundary against a malicious maintainer or compromised controller. Generated programs and parsers run in separate restricted workers and receive neither that socket nor model credentials. Do not add host directories, privileged mode or network access to these workers.

## Enforced controls

- Local Host/Origin checks and a mutation header protect browser-facing operations. These do not protect against malware already running as the same local user.
- Material bytes, types, parsed output and parser resources are bounded. Project references and generated files are checked for identity, traversal and links. Imported prose/code is untrusted data, not permission to modify platform controls.
- Method approvals are immutable. Builds and runs bind method, code, data and model identities; a revision creates a new version.
- Historical tasks receive cutoff-limited input. Code owns accounting and validates proposed decisions; models cannot directly create fills or change balances.
- Generated task environments exclude credentials, private databases, personal logins and Docker authority. Workers restrict filesystem writes, CPU, memory, process count, duration, output and network access. Isolation checks fail closed.
- Inference is explicitly authorized and reserved before transport. Unknown billed outcomes keep their reservations and are not silently retried. Startup and saved-example browsing make no model calls.
- Untrusted text and generated source are displayed inertly, not executed in the browser. Example assets are explicitly selected and validated before bundling.

See [architecture](architecture.md), [Docker boundaries](docker-local.md), [materials](materials.md) and [models/costs](models.md) for exact behavior and limitations.

## Residual risks

Prompt injection cannot be eliminated by instructions, structured output or containers. A model can misunderstand evidence, omit a rule, produce incorrect code or persuasive but unsupported reasoning. Review approved rules and use independent cases. Generated self-test output is not independent proof; even independent example checks cover only their stated cases.

Cutoff-limited input prevents supplied future bars from reaching a historical task, but cannot remove future information memorized during model training. Chart windows may omit older numeric history; visible dates and counts are disclosed. A model should report insufficient visual evidence rather than claim to have seen omitted dates.

The native Windows workspace monitor is periodic, not a hard disk quota. Docker isolation relies on the host kernel, Docker runtime and trusted controller. Dependency/advisory checks cannot establish that those components have no unknown vulnerabilities. Windows checks do not certify macOS or Linux hosts.

Model requests transmit the authorized project context to the selected provider. Local receipts, materials and databases may contain private content even when credentials are protected. Back up and protect the complete data location. Container session keys stay in memory; optional native Windows persistence uses DPAPI. An explicitly selected environment file is managed by the operator, not an encrypted application vault.

## Before sharing

Review actual files, example text, charts, media, build outputs, image layers and Git history—not only ignore rules. Do not share private databases, raw model transcripts, credentials or source data without permission. Public static assets remain downloadable even if hidden by the interface.

The public website serves static saved-project records and media; live model tasks run only in the local application with the operator's credentials. Software licensing, data/media rights and publication approval remain separate concerns. If a credential is exposed, revoke it; deleting a file does not revoke access or erase published history. Detailed findings and test evidence belong in private audit records; no statement here is a guarantee of zero risk.
