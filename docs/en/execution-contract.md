# Generated project execution contract

[English](execution-contract.md) | [简体中文](../zh-CN/execution-contract.md)

## strategy-v1

Generated standard-library Python projects declare `execution.json` and implement `strategy.py:decide(context)`. Construction validates the manifest and two independent synthetic decision inputs in isolation. Generated tests and these checks are not proof that every approved rule is implemented faithfully; review method-specific acceptance cases. A method with missing executable entry, exit, sizing or model criteria must be clarified, not filled with platform trading defaults.

All fields below are required. Unknown fields are rejected. The manifest is:

```json
{
  "schema": "strategy-v1",
  "entrypoint": "strategy.py:decide",
  "warmup_bars": 20,
  "history_bars": 21,
  "responsibilities": {"code": "Approved entry, exit and integer-share sizing rules", "model": null},
  "judgment": null
}
```

These numbers illustrate the format, not recommended trading rules. `warmup_bars` is 0–500 prior sessions; `history_bars` is 1–501 visible sessions including the current one, and must exceed warmup. The project owns its required values. Each decision receives at most `history_bars` per selected symbol. Supported historical data is the installed, validated US stock/ETF catalog, not arbitrary instruments or downloaded-on-demand data.

`context` contains `schema`, `cutoff` (YYYY-MM-DD close), `bars` (symbol → ordered OHLCV objects with date/open/high/low/close/volume), `account` (`cash`, `equity`, `positions`: symbol → integer shares), `state` (previous strategy JSON state) and `previous_orders` (the preceding decision's orders after next-open execution). Each order includes `id`, `decision_id`, `signal_date`, `symbol`, `action`, `quantity`, `status`, `reason`, `explanation`; filled orders also include `date`, `price`, `fee`, `gross`. Code cannot access future bars, full market files, other projects, host files, credentials or network. Account and fill records are observations, never mutation authority.

`decide` returns exactly:

```json
{
  "proposals": [{
    "symbol": "SPY",
    "action": "buy",
    "explanation": "Approved rule identifier and why its inputs satisfy it",
    "sizing": {"shares": 3},
    "judgment": null
  }],
  "state": {"SPY": {"signal_anchor": 100.25}}
}
```

Again, share count and anchor are format examples, not platform defaults. Empty proposals are valid. Actions are `buy`, `sell`, `hold`; buy/sell require positive integer shares, hold requires zero. At most one proposal per selected symbol; list order is preserved. Explanation is 1–2,000 characters. Account checks precede model calls when possible and repeat at actual fill prices. No partial size adjustment is invented: an unaffordable next-open gap cancels the entire order. Sells cannot exceed held shares. Fills use the next selected trading session's open; fees and gross amounts use decimal half-up cent rounding. No terminal liquidation is synthesized. Final-session orders remain unfilled. Fees are an explicit run assumption, not a stop/target rule.

State is an opaque JSON object, at most 16 KB and depth eight. Retain entry anchors, counters or other method-owned metadata here, and reconcile them with `previous_orders` and actual positions before treating an entry as filled. State cannot write balances or files, and is preserved in saved results. Output must be a single JSON object, at most 64 KB, with no extra stdout logging, NaN or duplicate JSON keys. The historical decision workspace is read-only: creating files or changing source/input is denied before execution. Construction remains writable in its separate scope. No package installation or file persistence is allowed; use state.

## Optional model judgments

### Optional managed account policy

For approved risk-sized entry plans, the manifest may additionally declare `account` with all fields: `mode: "risk-managed"`, `risk_fraction`, `max_weight`, `max_positions`, `entry_gap_limit`, `commission`, `slippage`, `progress_units`, `stagnation_sessions`, `trailing_stop_units`. These are method choices, not platform defaults. The run fee must equal the approved commission. Without this policy the fixed-share behavior above remains unchanged.

Managed buy proposals use `sizing: {"shares": 0}`, a finite numeric `priority` (larger first, symbol breaks ties) and ranked `candidates` (1–10). Each candidate has a unique `candidate_id`, positive `stop`, `target`, `volatility_unit`, `dates` (named ISO dates in visible history), and bounded JSON `facts`. Require `stop < current close < target`. The shared account calculates integer shares using approved risk, weight and available cash at the allowed gap price, including commission; reserves cash before later opportunities; and never lets the strategy set balances or fill prices.

Execution reuses the shared account arithmetic: prior orders fill next open with slippage, then close-based stop/target/trailing/progress exits are evaluated, then new entry proposals are ranked. Held and pending positions consume slots. An entry outside its gap/stop/target interval cancels without resizing. A progress exit counts sessions without a gain of `progress_units × volatility_unit`, not unconditional holding age. Exit decisions have their own traceable IDs; final-session exits remain unfilled. Context also exposes `available_cash` and `position_details`. Managed explicit sells must close the full existing position; partial exits use a fixed-share method instead. Model judgments cannot alter candidate geometry or account policy.

Only methods that require model judgment set `responsibilities.model` to a description and `judgment` to:

```json
{
  "criteria": "The approved project-specific rubric with explicit pass/fail evidence requirements",
  "trigger": "When this approved method requests a judgment",
  "tools": ["read_bars", "price_facts"],
  "uncertainty": "skip",
  "input_mode": "text_only"
}
```

The corresponding proposal's `judgment` is a 1–2,000-character reason to apply this rubric; null means code-only for that proposal. The approved method must define this trigger, not delegate its invention to the platform. `uncertainty` is `skip` or `stop`. Code owns sizing and exits unless the approved method explicitly calls for an exit judgment. A hold cannot request inference.

`input_mode` defaults to `text_only` for backward compatibility. Set `chart_and_text` only when the approved method needs visual chart judgment. The trusted controller draws the proposal symbol's latest at most 120 bars from already-visible cutoff-limited history: 1024 × 640 metadata-free RGB PNG (`ohlcv-v1` rendering, `rgb-png-v1` normalization), linear raw OHLC candles and volume, readable covered dates and actual as-of date. Earlier visible bars omitted from rendering are counted in metadata; numeric history remains available under the unchanged text/tool limits. There are no pattern-specific markers, generated-code image bytes, user-uploaded examples, external URLs/paths, future bars or benchmark data in the chart. Pure code and text judgments remain supported; old approved artifacts and results are not migrated or rewritten.

Chart pixels and text go only to the independently assigned execution model after selected-model image opt-in and explicit budget authorization. [Image policies and conservative reservation](materials.md#visual-interpretation-and-model-selection) are shared with builder clarification. Unsupported capability/billing, invalid image data, budget exhaustion and cancellation stop requests rather than becoming trading rejections. Each request records image policy, count, dimensions and digest. Stored run evidence contains the exact prepared/sent PNG and its source dates, cutoff, data hash and rendering bounds. Private local storage permits at most 1,000 chart files / 512 MiB per run; each normalized image is at most 512,000 bytes. Serving requires a matching saved decision and digest; it cannot read arbitrary paths. A valid saved image is not proof that a failed or cancelled request reached a provider; inspect its request status.

The decision inspector shows charts beside judgment/trade evidence. Browsing never calls a model. Evidence-to-chat includes saved chart identity/rendering provenance and explicitly omits chart pixels; it does not implicitly attach images. The separate reviewed-example exporter allowlists PNG bytes with matching decision/source metadata, never arbitrary run files. The packaged examples use this export path; additional exports require their own content and rights review.

Model output is exactly `{verdict, reason, evidence}`. Verdict is `pass`, `fail` or `insufficient_evidence`; reason is 1–3,000 characters and evidence is 1–20 `{symbol,date}` references actually present in visible bars. A valid fail is different from insufficient evidence, invalid output, missing evidence or infrastructure failure. Errors stop the run, retain evidence/costs and never silently become no-trade or retries.

The only permitted tools are `read_bars` and `price_facts`. Both require exactly `symbol`, `start_date`, `end_date` within supplied visible history, maximum 120 bars. Facts return first/last close, high/low and mean volume. No filesystem, internet or arbitrary calculator is exposed. Simple judgments permit one tool round (up to two tools) followed by one final answer, two requests and 1,500 output tokens per request. Historical runs permit at most 1,000 model requests within the project budget. Model knowledge may contain future training information; dated-tool restrictions cannot erase it.

For managed candidates, `judgment.rubric` maps 1–5 criterion names to `{description, start_anchor, end_anchor}`; anchor names refer to each candidate's `dates`. The model must return exactly `{"assessments": {"candidate-id": {"criterion": {"verdict", "reason", "evidence"}}}}`, covering every offered candidate and criterion. All evidence dates must lie inside that criterion's fixed region. Code aggregates checks: any fail → fail; otherwise any insufficient evidence → insufficient evidence; otherwise pass. `review_nonpass: true` requests one review of every non-pass candidate even if another already passed. The first ranked final pass wins. Review cannot alter anchors or force acceptance.

`repair_once: true` authorizes one correction of a saved malformed candidate response, never a retry of an unknown transport outcome. Each primary/review stage permits at most three requests including its one tool round and repair, at most 4,096 output tokens per request. Receipts retain stage identity and invalid outputs. Candidate judgments receive only their symbol's cutoff bars. Optional `judgment.history_bars` sets a separate model-visible history length (1–501, no greater than the top-level calculation history); it limits text, tools and charts together. For example, top-level `history_bars: 170`, `warmup_bars: 169`, and judgment `{history_bars: 160, chart_history: "declared"}` supply 170 bars to strategy calculations but only the latest 160 to the model and its chart. This is supported, not a conflicting method requirement. When the judgment override is absent, `chart_history: "declared"` renders the complete top-level history. Each candidate receives a controller-rendered `ohlcv-v2` chart with fixed dated markers; defaults preserve old 120-bar `ohlcv-v1` records. Candidate charts allow up to 10 images / 8 MiB wire data, with the same selected-model opt-in and conservative cost accounting. Each run permits 1,000 stored chart files / 512 MiB; original chart identities remain readable.

Runs require the saved execution role and fresh explicit spending authorization only when the manifest includes judgment. They never borrow the builder model. All requests reserve the same project budget used by conversation/construction, persist successful raw receipts privately before validation and retain unknown-outcome reservations. Cancellation stops before the next decision/model round; an in-flight request may complete and incur cost. Restart marks interrupted and never resumes spending automatically.

## Provenance and limits

New runs require a completed sealed build tied to an approved version. Legacy builds remain browseable but must be rebuilt to gain this contract. Method, files, manifest, market snapshot, model parameters and assumptions are frozen and hashed; tampering blocks execution. Raw full market data stays in the trusted run store; only per-cutoff slices enter a fresh isolated directory. Native Windows defaults to MXC; the maintained Compose launch selects Docker workers. Both fail closed if isolation is unavailable. See the [runtime verification matrix](docker-local.md#verification-matrix-and-troubleshooting) for the environments actually exercised.

Capacity: 100 catalog symbols, 756 sessions, 100 saved runs per project, 16 MiB frozen input and 160 MiB combined record. Runs above 10 symbols or 100 sessions store lossless cutoff references into their frozen market snapshot instead of duplicating rolling histories every day; result evidence is bounded to 128 MiB. Smaller inline-evidence runs retain the 12 MB result bound. Inspection reconstructs only each decision's visible interval and verifies its original input hash and frozen market identity. Legacy saved inputs remain readable.

Each isolated call permits an 8 MiB cutoff context, 20 seconds and 64 KB captured output, with the existing process-tree memory boundary. Before each session, conservative reservation covers permitted inputs, proposals, model/tool evidence and the terminal checkpoint. If it cannot fit, the run stops before that session's fills or requests, cancels pending orders and preserves completed evidence/spend. Read-only isolation is the filesystem-output boundary. Host inspection/cleanup permits 512 entries, depth eight, an 8 MiB context plus 2.5 MB other files (1.5 MB each), and two seconds per phase. An anomalous scope is retained for inspection rather than traversed/deleted without bounds.

The inspector exposes every saved input symbol with 40 bars per page, plus approved judgment criteria, state, prior fills and complete saved model-tool arguments/results in expandable 12,000-character pages. Quoting attaches a validated same-project run/decision reference, not browser-supplied evidence. On the user's separately authorized conversation request, the trusted backend resolves actual saved inputs, sizing/fills/state, model evidence, approved method/manifest and Python source excerpts, with an 80 KB handoff cap and explicit omissions (including truncated JSON/code and omitted bars). The builder must not claim to inspect omitted context or modify the original run. Quoting never sends automatically or reuses execution authorization. Results remain separate from ordinary project polling. Historical prices use the disclosed frozen split-adjusted, non-dividend-reinvested source convention; this is not live trading or a promise of returns.
