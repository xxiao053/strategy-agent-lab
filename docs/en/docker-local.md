# Docker local distribution

[English](docker-local.md) | [简体中文](../zh-CN/docker-local.md)

The maintained Docker distribution includes the web build, backend dependencies and a separate Python worker image. It explicitly selects Docker; missing isolation never falls back to unrestricted host execution. The native Windows launcher still defaults to MXC.

## Start and stop

Install Docker Desktop or Docker Engine 25+ with Compose v2. Use Linux containers and leave Docker's default seccomp profile enabled. Start Docker before running either command from the downloaded repository:

```powershell
.\scripts\start-docker.cmd
```

```sh
sh scripts/start-docker.sh
```

The scripts check the engine, build pinned images and wait for the local application. Open [127.0.0.1:8765](http://127.0.0.1:8765). Builds download public dependencies; startup does not open a browser, download market data or call a model.

The Windows entry works from Windows PowerShell 5.1, PowerShell 7 or Command Prompt, including paths containing spaces. It permits the bundled PowerShell script only in its child process; it does not permanently change your execution policy. Organization-enforced policies may still require your administrator. Only run a downloaded copy you trust.

Stop with `.\scripts\start-docker.cmd stop` (Windows) or `sh scripts/start-docker.sh stop` (POSIX). Replace `stop` with `restart` to restart. Updating uses the normal start command again. These commands do not remove data volumes. Do not use `docker compose down -v` unless you intend to delete saved data.

The named `lab-data` Compose volume persists projects, receipts, generated results and market sources. An explicitly chosen absolute directory can replace it by setting `LAB_DATA_PATH` before launching; it must be accessible to Docker. This selects storage, not a migration: existing native data is never moved or rewritten. The backend's `LAB_DATA_ROOT` separates runtime data from immutable source. Stop the app before backing up its complete data volume; receipts can contain private method and provider content.

## Credentials and first historical run

Use **Model settings** to create your own connection. Container/non-Windows sessions store keys only in backend memory, not a plaintext vault. After restarting, use **Re-enter key** on the existing connection: model, prices, project bindings and historical requests remain intact. An active connection cannot be replaced. Saving or renewing never calls a model. Optional environment credentials require explicit selection; the maintained Compose file deliberately forwards no provider secrets. Windows DPAPI persistence is only offered where supported, not inside the Linux controller.

After approving and building a method, open **Runs & results**, choose symbols/dates and select **Prepare data**. This explicitly contacts the fixed Yahoo daily-data endpoint, includes the build's warmup requirements and preserves checksummed snapshots. It performs no inference, interpolation or arbitrary-URL fetching. Preparation is limited to 100 catalog symbols, 756 sessions within 1,200 calendar days, two concurrent fetches, one attempt per symbol and a 4 MB response cap. Failed symbols are shown separately; provider data revisions or unavailable dates may prevent a run. Then choose cash/fees and start the historical run, separately authorizing any required execution model.

## Trust boundary and limits

The trusted controller has the Docker socket and therefore authority over the Docker host. Only run reviewed application source locally; this is not a public hosted service or a protection against a malicious controller. No privileged Docker-in-Docker service is used. Generated code and material parsers run in separate workers, never the controller.

Task workers run as UID/GID 10001, with no network/ports, all Linux capabilities dropped, no-new-privileges and default seccomp. They have a read-only root, one CPU, 256 MiB memory/no extra swap, 64 PIDs, bounded command output, and bounded lifetimes. Construction uses a 16 MiB/512-inode task tmpfs and 8 MiB temporary filesystem. Temporary storage retains noexec; the pinned SDK path validator runs through the read-only system shell using verified script content, not a task-editable helper file. No checkout, home, API key, database, login or Docker socket is passed to workers.

One Docker construction permits up to 50 model requests and 100 tool operations within 480 seconds. These are ceilings, not promised work: remaining budget, context size and other limits may stop it earlier. A model roundtrip is one request and response; reading files, editing and testing may require several. Native MXC construction has a separate 16-request ceiling.

Native and Docker construction each allow up to **2 MiB (2,097,152 bytes)** for both the incoming and normalized provider request. This transport/resource limit is not a model's token capacity or an injection defense. Requests are not padded to the limit; actual content and the remaining authorized budget still matter. Before dispatch, reservations apply a 1.5× safety margin to configured token pricing and any supported long-context tariff. Completed usage is priced without that margin, including configured or supported cache rates; missing usage/pricing retains the reservation. Budget occupancy, usage-priced amounts and provider bills are distinct: no provider invoice integration is available, and old records remain unchanged. See [cost accounting](materials.md). Native `gpt-6-luna` uses its documented context window and begins local history compaction around 200,000 tokens; unknown native models retain the smaller fallback until their capacity is verified. Docker saved-source recovery is available, but automatic in-session compaction is not yet implemented. These settings do not guarantee completion of an arbitrarily long build.

Starting another build reuses eligible saved source as an unverified starting point: failed attempts must belong to the same approved method version, while a completed build may support a new version. The builder is instructed to inspect and repair it, not recreate the project. Failed work is collected only when safe; timeout or revoked resources can prevent recovery. Complete saved code from a failed same-version attempt is independently checked first. If it passes, a new completed verification record is created without a model call. Earlier failures, approvals and costs remain unchanged; no paid request resumes automatically.

Historical decisions receive only current-cutoff code/input through a task-only tmpfs volume mounted **read-only** in the evaluator. A trusted seed holder keeps that volume alive until evaluation ends; it executes no generated program. Containers and volumes are inspected before use. Only bounded regular allowlisted outputs are collected; links, devices and escaping paths fail closed. Collected results survive task deletion. Startup cleanup targets this installation's labeled unfinished resources only. Budgets are reserved before every model request; responses are saved before interpretation, tracing/retries are disabled and unknown costs remain reserved.

Native MXC construction also bounds output traversal and monitors workspace file counts/bytes while its process tree runs. The native monitor can overshoot between checks; it is **not** a hard filesystem quota. Docker's quota boundary has been tested on the Windows Docker environment below; other installations still require acceptance.

## Verification matrix and troubleshooting

| Environment | Evidence |
| --- | --- |
| Windows native MXC | Existing operational construction/evaluation checks; remains native default |
| Windows Docker Desktop, Linux/amd64 images | Engine 29.9.3 / Compose 5.7.0: scoped worker isolation/resource/cleanup, real model construction, saved-source recovery, independent tests and visual historical execution; rebuilt full-controller images also passed fresh-volume startup, material parsing, synthetic historical execution, scripted SDK tools and restart/key-renewal checks |
| Linux/macOS Docker | Supplied distribution, not platform-accepted; do not infer support from the Dockerfile |

The worker has passed scoped actual-engine checks for tmpfs quotas, read-only mounts, bounded output, timeout/cancellation and SDK shell/patch operations. Automated SDK tests use scripted responses, not model inference. Separate authorized acceptance used real model-generated cup code, independent method checks, image-based historical judgments and a versioned position-size change. The full controller image has also executed those scripted tools and a synthetic code-only historical fixture through separate workers, without author credentials or host source/data mounts. Projects, material identities, run results and connection bindings survived controller recreation; session keys required renewal as intended. A fresh-volume controller also passed creating independent copies of both bundled examples, approving their remapped source references, verifying starter code in separate workers and preserving project hashes across restart; no provider calls or author database were used. These checks are not a complete security audit or Linux/macOS acceptance.

**Engine unavailable:** start Docker in Linux-container mode; finish any required reboot. The workspace's **Isolated runtime** status reports engine/image readiness, not an isolation audit. **Missing image:** run the maintained start command. **Port busy:** stop another app on 8765 or change only the localhost host port in Compose. **Missing key after restart:** renew the saved connection, without deleting it. **Data preparation fails:** check selected trading dates/provider availability; existing corrupt or partial sources are not overwritten. **Task interrupted:** evidence and reservations remain; no task or paid request resumes automatically. Never loosen isolation or mount the entire data volume into a worker to bypass an error.
