# Public Health Outbreak Monitoring System

A monitoring pipeline that watches public health surveillance feeds, detects anomalous outbreak signals against season-aware baselines, corrects for reporting lag, and surfaces prioritized alerts through a console and push digest.

**Status:** in active development · capstone project · [decision brief](docs/decision-brief.pdf) · [ADRs](docs/adr/)

`Python` · `Firecrawl` · `Redpanda` · `AWS S3` · `Snowflake` · `Snowpipe Streaming` · `dbt` · `Dagster` · `React/Next.js`

---

## What this is

Public health surveillance data is slow and it lies at the edges. Most CDC feeds update weekly, confirmed case counts lag real illness by weeks, and the most recent weeks are always incomplete — which makes a rising outbreak look like a declining one right at the moment you'd want to act.

This system is built around that constraint rather than around it being inconvenient. It is deliberately **not** a real-time pipeline. It does two things well:

1. **Season-aware baselining** — establishes what "normal" looks like for a given disease, in a given state, in a given week of the year. An alert means *unusually high for this week*, not just *high*.
2. **Reporting-lag nowcasting** — learns how much each recent week is likely to be revised upward, and estimates where counts actually are, with an uncertainty band. This is what prevents the false-comfort "cases are declining" reading that incomplete recent data produces by default.

Everything else in the stack — ingestion, warehousing, orchestration, the console — exists to make those two techniques possible and honest.

## The finding this project is built to produce

Applied to the 2026 cyclosporiasis outbreak using **only data available at each point in time**, does the monitor flag an anomalous produce-linked signal before it reaches national news — while correctly suppressing the false declining reading the reporting lag would have produced?

The backtest is the credibility proof, so its success criteria are pre-registered here, before it runs:

| Criterion | Target |
|---|---|
| Lead time vs. mainstream coverage | Reported as a range across alert thresholds, not a single number |
| False-alarm rate | Reported at each threshold in the same sweep (precision/recall) |
| Earliness delta | Days the crawl lane led the NNDSS API for the same signal — may be zero |
| Definition of success | A defensible lead at *some* threshold with a false-alarm rate a real operator would tolerate |

A target defined after seeing the outcome is self-deception. If the lead time is modest, that is the result and it ships as written. If the earliness delta comes back at zero, that is a reportable finding about the crawl lane, not a failure to hide.

## Architecture

```
                    ┌──────────────────────────────────────────┐
   API lane ───────▶│                                          │
   (NNDSS, CDC Rt)  │                                          │
                    │   S3 landing zone                        │
   Revision lane ──▶│   snapshot-dated keys, append-only       │──▶ Snowflake RAW
   (batch diff)     │                                          │        │
                    │                                          │        │
   Crawl lane ─────▶│                                          │        │
   (FDA CORE,       └──────────────────────────────────────────┘        │
    state pages)                                                        │
                                                                        ▼
   Event lane ──────▶ Redpanda ──▶ Snowpipe Streaming ──────────▶ Snowflake RAW
   (HAN, recalls)                                                       │
                                                                        ▼
                                                          dbt: staging → intermediate
                                                                        │
                                            ┌───────────────────────────┤
                                            ▼                           ▼
                                   marts: baseline, nowcast,     corroboration
                                   anomaly, backtest                    │
                                            │                           │
                                            └───────────┬───────────────┘
                                                        ▼
                                            detection (Python)
                                                        │
                                                        ▼
                                        frozen payload contract
                                                        │
                                            ┌───────────┴───────────┐
                                            ▼                       ▼
                                      React console           alert digest

                          Dagster orchestrates the entire chain
```

### Ingestion lanes

Four lanes, each chosen by what the source actually offers rather than by a uniform pattern:

| Lane | Sources | Access | Why this pattern |
|---|---|---|---|
| **API** | NNDSS weekly tables, CDC CFA epidemic-trend | Socrata API, scheduled poll | Publishes weekly; polling matches the cadence |
| **Revision** | NNDSS poll-over-poll diff | Batch job → append-only table | The diff inherits the poll schedule, so a broker would add cost without adding anything the model consumes |
| **Crawl** | FDA CORE outbreak table, state/county dashboards | Firecrawl, timed | No API exists; these pages carry the leading edge |
| **Event** | HAN advisories, FDA recalls, state advisories | RSS/Firecrawl → Redpanda | Genuinely irregular arrival with no schedule to poll against |

### The four marts

1. **Seasonal baseline** — expected count and range by disease × jurisdiction × week-of-year, learned from historical years. Must degrade gracefully at near-zero off-season counts, since ratio-based scores explode at small denominators and cyclospora sits near zero outside summer.
2. **Nowcast** — applies the learned lag profile to recent weeks, with an uncertainty band. Learned from the append-only revision log rather than re-derived snapshot comparisons at query time.
3. **Anomaly signals** — nowcast vs. baseline → score, fired flag, reason code, corroboration count, earliness delta. This mart *is* the payload both consumers render.
4. **Backtest evaluation** — replays detection logic on point-in-time data. The credibility proof.

## Source tiering

In an alerting system, a bad source is worse than a missing one. Sources are tiered explicitly:

- **Tier 1 — drives alerts.** Federal APIs and official state/county/agency pages. Crawled only where no API exists.
- **Tier 2 — corroboration, never fires alone.** The advisory and recall event lane. These raise or damp confidence on a Tier 1 signal; they never originate one.
- **Tier 3 — deliberately excluded.** General news aggregators and unverified trackers. Named here with the reason rather than quietly omitted.

## Architecture decisions

Full ADRs live in [`docs/adr/`](docs/adr/). The load-bearing ones:

**Batch where scheduled, stream only where arrival is irregular.** The count feeds publish weekly, so streaming them would be theater — and the same logic applies to their deltas. The revision diff inherits the poll's schedule, so it runs as a batch job appending change records to a revision log. Redpanda is carried by the event lane alone, where arrival genuinely has no schedule.

**The event lane's existence is conditional on measured arrival rate.** Before the first build weekend, the actual arrival rate of the candidate feeds is counted over a month. If it supports bursty irregular arrival with real fan-out, the broker is justified. If it doesn't, the lane drops to a Dagster sensor and the ADR records the measurement and the cut. Sources are not added to justify a tool.

**No LLM in the alerting path.** An LLM classifier over FDA CORE investigation text was scoped and removed. FDA CORE is a Tier 1 source, and probabilistic classification on an alert-driving path is where non-determinism is least welcome. A deterministic extractor over a locked scope is more defensible. The consideration and rejection are the deliverable.

**Snapshot-dated S3 keys, never overwrite.** Keys carry the pull date, not just the reporting week, because CDC revises prior weeks as late cases arrive. Overwrite-on-rerun would destroy the exact signal the nowcast learns from.

**Firecrawl only where data lives exclusively in pages — and the earliness is measured.** Every crawled item is stamped with a first-seen timestamp, and the backtest reports the delta against NNDSS first-appearance. A claim about tool fit that carries a number is worth more than the same claim asserted.

**Disease-as-config from the first commit.** Disease is a dimension carrying seasonality type, expected lag, and alert-eligibility — not hardcoded logic. Adding one is a config line plus a backfill.

**Frozen payload contract.** The anomaly mart emits one schema, frozen before either consumer is built. The console and the alert digest are peer renderers of it, which lets frontend work run parallel to detection instead of queueing behind it.

## Scope discipline

Deliberately constrained, with the reasoning recorded rather than discovered later:

- **One baseline method and one lag model** that can be explained end to end. Depth over breadth.
- **2–3 diseases chosen for contrast, not coverage** — cyclosporiasis (seasonal, foodborne, long lag) plus a low-count sporadic disease that tests robustness against small-sample false alarms.
- **Corroboration is a scoped join** on (disease, state, date window). The moment it becomes fuzzy matching it is a second project.
- **No websocket/push updates.** Over-engineering for daily-moving data. The console shows a real "data current through week N" timestamp sourced from the latest snapshot, never wall-clock render time.

## Known risks

| Risk | Mitigation |
|---|---|
| Backtest lead time is not under my control | Pre-registered success range and threshold sweep; a modest lead still ships as a credible artifact |
| Corroboration-join creep into entity resolution | Scope locked to a (disease, state, date window) match; anything richer is explicitly out |
| Off-season zero counts producing garbage scores | Verified against historical off-season data before the nowcast build starts |
| Earliness delta comes back near zero | Reportable finding, not a failure — becomes a cut-with-evidence decision on the crawl lane |
| Streaming learning-curve tax | One brokered lane only, built after the arrival-rate check confirms it should exist |

## Data sources

All public, all free. No API keys required for the core sources.

| Source | Provides |
|---|---|
| NNDSS weekly tables (data.cdc.gov) | The spine — notifiable disease counts by state × week, provisional and revised as late cases arrive |
| CDC CFA epidemic-trend (Rt) | Model-ready respiratory signal; second detection pattern |
| FDA CORE outbreak table + CDC foodborne pages | The leading edge, before a signal becomes a number in NNDSS |
| CDC Health Alert Network (HAN) | Urgent advisories, genuinely event-shaped |
| FDA / USDA FSIS recall feeds | Product-level recalls; independent corroboration |
| State / county health dashboards | Hotspot detail at county grain, ahead of federal aggregation |

## Scope boundary

This is early-warning risk monitoring on public data. It is **not** food-safety certification and makes no regulatory or clinical claim. The system surfaces public signals faster; it does not adjudicate safety.

## Repository layout

```
├── docs/
│   ├── decision-brief.pdf       # full project brief
│   └── adr/                     # architecture decision records
├── ingestion/
│   ├── api/                     # Socrata extractors
│   ├── revision/                # poll-over-poll batch diff
│   ├── crawl/                   # Firecrawl lane, first-seen stamped
│   └── events/                  # advisory/recall feeds → Redpanda
├── dbt/
│   ├── models/staging/
│   ├── models/intermediate/     # harmonize, revision history, lag profile
│   └── models/marts/            # baseline, nowcast, anomaly, backtest
├── detection/                   # baseline, nowcast, scoring
├── orchestration/               # Dagster definitions
├── console/                     # React/Next.js
└── config/
    └── diseases/                # disease-as-config dimension
```

---

*Portfolio capstone. The client scenario in the decision brief is illustrative; the backtest target is a real evaluation against the live 2026 cyclosporiasis outbreak.*
