# Cup-with-handle: an agent workflow demonstration

[English](demonstration.md) | [简体中文](../zh-CN/demonstration.md)

This example shows how an approved investment method moves through a complete agent system. It is not a study of whether adding an LLM makes a strategy more profitable.

This is a complete **historical execution example**, with method configuration, model assessments and simulated transactions. See [Product direction](product-direction.md).

[Watch the captioned walkthrough](../media/walkthrough.mp4) · [Revision GIF](../media/revision.gif) · [Bilingual captions](../media/walkthrough.bilingual.srt)

The video browses the genuine projects below in the local workbench. It uses a full-window English interface and English/Chinese captions, with idle gaps removed; it does not depict new model calls.

## Full builder-generated example

In a fresh local installation, both included Builder projects offer **Create editable copy** for the selected method version. The new draft carries reviewed excerpts and starter code, not source approvals or historical results. Review, configure and build it as your own project; see [the continuation workflow](getting-started.md#continue-from-an-included-example). Static playback remains read-only.

**My projects → Cup & handle · 718 sessions** opens a genuine Builder project covering the original 40 instruments and 2024-01-02–2026-11-10 interval (718 sessions). The Builder received the complete method and numeric reference, clarified and corrected the draft, and generated a separate strategy-v1 implementation. It uses the original numerical, account, cost, exit and model-review configuration; it does not reuse the original result as its own output.

The portable package at `examples/builder/cup-complete/` contains the real conversation, approved rules, generated files, self-test report, independent-check summary, full daily equity curve, 56 fills, decision evidence and 105 derived charts. It can be inspected without credentials. When the native project exists locally, its entry opens the actual editor and complete request/build/run history; the static preview uses the read-only portable record in the same workbench layout. The full project's conversation is presented in English; two translated historical messages retain their original text in source details. Presentation changes do not alter approved methods or execution results.

| New generated run | Value |
| --- | --- |
| Initial / ending equity | $100,000 / $176,188.30 |
| Total return | +76.19% |
| Maximum drawdown (daily close) | 36.14% |
| Model decisions / requests | 60 / 99 |
| Simulated commission | $1,719.55 |

Returns include simulated commission and slippage, not model API charges. Drawdown is peak-to-trough daily closing equity loss, not intraday drawdown. The saved run includes two bounded response-format corrections. The example is a reviewed selection, not a claim of first-attempt success or total project cost. Independent checks cover 26 implementation cases and all 718 sessions' cutoffs, fills, fees, holdings and equity; generated self-tests remain separately labeled. These checks do not guarantee future performance or correctness on every input.

The original saved result remains unchanged below. Different fresh model judgments and implementations can produce different outcomes; the return gap has not been causally attributed.

## Smaller revision example

The smaller NVDA Builder project is retained separately under `examples/builder/nvda-revision/` and **My projects → NVDA · 100 to 50 shares**. It uses the core cup/handle thresholds and three shape criteria, generates a strategy-v1 project, runs visual historical judgments and revises fixed sizing from 100 to 50 shares. It demonstrates revision, not the full original specification. Both saved runs and their original method version numbers (v2 and v3) are preserved; the portable selection does not claim to contain every intermediate attempt. The original dedicated cup execution reference remains accessible from the sidebar footer.

| Setting | Original included example | Builder acceptance |
| --- | --- | --- |
| Instruments / dates | 40 instruments; 2024-01-02–2026-11-10 | NVDA; 2024-01-02–2024-02-15 |
| Starting cash / sizing | $100,000; risk-based quantity | $10,000; fixed 100 shares, revised to 50 |
| Model review | Shortlist of up to three; conditional second review | First-ranked candidate only; no second reviewer |
| Execution costs | 0.05% fee and 0.05% slippage; 1% entry gap limit | 0.05% fee; no slippage or extra gap policy |
| Exits | Close-based stop/target and 30-session volatility-progress rule | Close-based original stop/target; no progress exit |

Both use 25–120-session cups, 5–30-session handles, 8% rim tolerance, 6–50% cup depth and the same cup/handle/coherence criteria. The full systems are not identical. This smaller scope validates construction, inspection and revision, not reproduction of the original returns. Fresh model judgments can differ even when their criteria are unchanged; a 50-share revision does not imply exactly half a prior run's profit.

## Follow one decision

1. **Method:** define the cup, handle and coherence rubric, plus numeric and execution parameters.
2. **Program:** identify a small set of fixed shapes, verify numeric conditions and check account eligibility.
3. **Agent:** inspect the marked shape, request scoped data/metrics/chart tools where useful, and return dated evidence.
4. **Validation:** require every offered candidate and validate the assessment. Conditional review can reconsider non-pass findings.
5. **Account:** size and execute permitted orders, manage exits and track the shared portfolio.
6. **Inspection:** follow the candidate, judgment and order through the workspace.

See [result.json](../../examples/cup-handle/result.json) for representative accepted, rejected and skipped decisions, the daily equity curve and completed trades. [config.json](../../examples/cup-handle/config.json) contains all method parameters; authorization is disabled.

## Recorded run

| Item | Value |
| --- | --- |
| Instruments | 40 US stocks and unleveraged ETFs |
| Interval | 2024-01-02–2026-11-10; 718 sessions |
| Model | OpenAI gpt-6-luna, low reasoning |
| Capital | $100,000 |
| Ending equity | $236,755.98 |
| Return / maximum drawdown | +136.75598% / −29.35018% |
| Buy fills / closed trades / open positions | 32 / 31 / 1 |
| Average exposure | 68.38% |
| Model requests / estimated cost | 257 / $0.4756 |

The method/configuration was selected and tuned for demonstration. Returns are historical simulation, not a forecast or an independently validated strategy. Concentration is permitted: this configuration allows a 100% per-instrument entry cap and a 25% planned risk budget. It is not a risk recommendation.

## Rule ownership

Code calculates the candidate's fixed handle-low stop and target (breakout level plus five cup heights in this example), position quantity, costs and exits. Signals use the close; fills use the next open. The agent judges pattern quality, not portfolio size or sell timing.

The configured lack-of-progress exit observes 30 sessions without the required volatility-scaled progress, rather than selling merely because a position reaches a fixed age. Full thresholds are in the configuration.

## Read the result correctly

The run found 142 numeric candidate dates: 60 were skipped before inference and 82 received model judgment. Of those 82, 48 passed final judgment and 34 were rejected. The account filled 32 buys. The original saved run includes seven accepted opportunities without orders and nine next-open gap cancellations; it is not rewritten to manufacture a tidier history.

Inspectability is the acceptance criterion: decisions, execution and accounting must correspond. The demonstration does not compare itself with a numeric-only strategy.

The public snapshot is derived output, not the raw market feed or full local database. Exact replay requires the original local inputs and response receipts; new downloads or new model calls can differ.
