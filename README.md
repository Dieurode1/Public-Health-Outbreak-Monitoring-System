<div align="center">

# 🦠 Public Health Outbreak Monitoring System

**Detects outbreak signals against season-aware baselines, corrects for reporting lag, and surfaces prioritized alerts — before the news does.**

[![Status](https://img.shields.io/badge/status-in%20active%20development-F4A261?style=for-the-badge)](.)
[![Project](https://img.shields.io/badge/portfolio-capstone-1F4E5F?style=for-the-badge)](.)
[![License](https://img.shields.io/badge/license-MIT-2A9D8F?style=for-the-badge)](LICENSE)

<br>

![Python](https://img.shields.io/badge/Python-3776AB?style=flat-square&logo=python&logoColor=white)
![Snowflake](https://img.shields.io/badge/Snowflake-29B5E8?style=flat-square&logo=snowflake&logoColor=white)
![dbt](https://img.shields.io/badge/dbt-FF694B?style=flat-square&logo=dbt&logoColor=white)
![Dagster](https://img.shields.io/badge/Dagster-4F43DD?style=flat-square&logo=dagster&logoColor=white)
![Redpanda](https://img.shields.io/badge/Redpanda-E3322D?style=flat-square&logo=apachekafka&logoColor=white)
![AWS S3](https://img.shields.io/badge/AWS%20S3-569A31?style=flat-square&logo=amazons3&logoColor=white)
![Next.js](https://img.shields.io/badge/Next.js-000000?style=flat-square&logo=nextdotjs&logoColor=white)
![React](https://img.shields.io/badge/React-61DAFB?style=flat-square&logo=react&logoColor=black)
![Firecrawl](https://img.shields.io/badge/Firecrawl-FF6B35?style=flat-square&logo=googlechrome&logoColor=white)

[Decision brief](docs/decision-brief.pdf) · [ADRs](docs/adr/) · [Backtest results](docs/backtest.md)

</div>

---

## 📌 The problem

> Public health surveillance data is slow, and it lies at the edges.

Most CDC feeds update weekly. Confirmed case counts lag real illness by weeks. And the most recent weeks are **always incomplete** — which makes a rising outbreak look like a declining one at exactly the moment you'd want to act.

<table>
<tr>
<td width="50%" valign="top">

### ❌ What naive monitoring shows

```
Week 24  ████████████████  412
Week 25  ██████████████    358
Week 26  █████████         241
Week 27  ████              108   ← "declining!"
```

*Reads as a resolving outbreak. Act accordingly.*

</td>
<td width="50%" valign="top">

### ✅ What lag-corrected nowcasting shows

```
Week 24  ████████████████  412
Week 25  ███████████████▒  358 → 371
Week 26  ██████████████▒▒  241 → 389
Week 27  ████████████▒▒▒▒  108 → 402   ← flat-to-rising
```

*Same data. Opposite conclusion.*

</td>
</tr>
</table>

This system is built **around** that constraint rather than pretending it isn't there. It is deliberately **not** a real-time pipeline — claiming real-time on lagged data is the tell of someone who doesn't understand the domain.

---

## 🎯 Two techniques carry the project

<table>
<tr>
<td width="50%" valign="top">

### 📈 Season-aware baselining

Establishes what *normal* looks like for a given **disease × state × week-of-year**, learned from historical years.

An alert means **"unusually high for this week"** — not just "high."

> Cyclospora sits near zero outside summer, so the baseline must degrade gracefully at small denominators where ratio scores explode.

</td>
<td width="50%" valign="top">

### 🔮 Reporting-lag nowcasting

Learns how much each recent week gets revised upward, then estimates where counts **actually are**, with an uncertainty band.

Prevents the false-comfort **"cases are declining"** artifact.

> Learned from an append-only revision log, not re-derived snapshot comparisons at query time.

</td>
</tr>
</table>

Everything else in the stack — ingestion, warehousing, orchestration, the console — exists to make those two techniques possible and honest.

---

## 🔬 The finding this project is built to produce

Applied to the **2026 cyclosporiasis outbreak** using *only data available at each point in time* — does the monitor flag an anomalous produce-linked signal before it reaches national news, while correctly suppressing the false declining reading?

> [!IMPORTANT]
> **Success criteria are pre-registered below, before the backtest runs.** A target defined after seeing the outcome is self-deception. If the lead time is modest, that is the result and it ships as written.

| Criterion | Target | Status |
|:---|:---|:---:|
| **Lead time** vs. mainstream coverage | Reported as a range across alert thresholds, never a single number | ⏳ |
| **False-alarm rate** | Reported at each threshold in the same sweep (precision/recall) | ⏳ |
| **Earliness delta** | Days the crawl lane led the NNDSS API for the same signal — may legitimately be zero | ⏳ |
| **Definition of success** | A defensible lead at *some* threshold, at a false-alarm rate a real operator would tolerate | 📌 locked |

If the earliness delta comes back at zero, that is a **reportable finding** about the crawl lane — not a failure to hide.

---

## 🏗️ Architecture

```mermaid
flowchart TB
    subgraph SOURCES["📡 SOURCES"]
        direction LR
        S1["NNDSS<br/>weekly tables"]
        S2["CDC CFA<br/>epidemic-trend"]
        S3["FDA CORE<br/>+ state dashboards"]
        S4["HAN · FDA/USDA<br/>recall feeds"]
    end

    subgraph INGEST["🔌 INGESTION LANES"]
        direction LR
        L1["<b>API lane</b><br/>scheduled poll"]
        L2["<b>Revision lane</b><br/>batch diff"]
        L3["<b>Crawl lane</b><br/>first-seen stamped"]
        L4["<b>Event lane</b><br/>irregular arrival"]
    end

    subgraph LAND["🗄️ LANDING + RAW"]
        direction LR
        S3B[("S3<br/>snapshot-dated keys<br/><i>never overwrite</i>")]
        RP{{"Redpanda"}}
        SF[("Snowflake RAW")]
    end

    subgraph TRANSFORM["⚙️ dbt TRANSFORM"]
        direction LR
        T1["staging"] --> T2["intermediate<br/><i>harmonize · revision history<br/>lag profile · corroboration</i>"]
    end

    subgraph MARTS["📊 MARTS"]
        direction LR
        M1["🟢 baseline"]
        M2["🔵 nowcast"]
        M3["🟠 anomaly"]
        M4["🟣 backtest"]
    end

    DET["🧠 <b>DETECTION</b><br/>scoring · corroboration modulation<br/><i>no LLM in the alerting path</i>"]
    PAY["📦 <b>FROZEN PAYLOAD CONTRACT</b><br/>reason code · corroboration count · earliness delta<br/>nowcast band · affected jurisdictions"]

    subgraph SERVE["🖥️ SERVE"]
        direction LR
        C1["React console"]
        C2["Alert digest"]
    end

    S1 --> L1
    S1 --> L2
    S2 --> L1
    S3 --> L3
    S4 --> L4

    L1 --> S3B
    L2 --> S3B
    L3 --> S3B
    L4 --> RP
    RP -->|"Snowpipe<br/>Streaming"| SF
    S3B --> SF
    SF --> T1
    T2 --> M1 & M2 & M3 & M4
    M1 & M2 & M3 --> DET
    DET --> PAY
    PAY --> C1
    PAY --> C2

    DAG["🎛️ <b>Dagster</b> orchestrates the entire chain"]
    DAG -.-> INGEST
    DAG -.-> TRANSFORM
    DAG -.-> DET

    classDef src fill:#E8F4F8,stroke:#1F4E5F,stroke-width:2px,color:#1F4E5F
    classDef lane fill:#FFF4E6,stroke:#F4A261,stroke-width:2px,color:#8A4B08
    classDef store fill:#E7F5EE,stroke:#2A9D8F,stroke-width:2px,color:#14514A
    classDef mart fill:#F3E8FF,stroke:#8B5CF6,stroke-width:2px,color:#4C1D95
    classDef core fill:#FFE8E8,stroke:#E76F51,stroke-width:3px,color:#7A2E1A
    classDef serve fill:#E8EEFF,stroke:#4F43DD,stroke-width:2px,color:#2A2496

    class S1,S2,S3,S4 src
    class L1,L2,L3,L4 lane
    class S3B,RP,SF,T1,T2 store
    class M1,M2,M3,M4 mart
    class DET,PAY,DAG core
    class C1,C2 serve
```

### 🛤️ Four ingestion lanes, each chosen by what the source actually offers

| | Lane | Sources | Access | Why this pattern |
|:---:|:---|:---|:---|:---|
| 🔵 | **API** | NNDSS, CDC CFA Rt | Socrata API, scheduled poll | Publishes weekly — polling matches the cadence |
| 🟢 | **Revision** | NNDSS poll-over-poll diff | Batch job → append-only table | The diff inherits the poll schedule, so a broker adds cost without adding anything the model consumes |
| 🟠 | **Crawl** | FDA CORE, state/county dashboards | Firecrawl, timed | No API exists; these pages carry the leading edge |
| 🔴 | **Event** | HAN, FDA/USDA recalls, state advisories | RSS/Firecrawl → Redpanda | Genuinely irregular arrival, no schedule to poll against |

> [!NOTE]
> **The event lane's existence is conditional.** Its arrival rate is measured before the build starts. If the feeds don't produce genuinely bursty traffic, the lane drops to a Dagster sensor and the ADR records the measurement and the cut. Sources are not added to justify a tool.

### 📊 The four marts

```mermaid
flowchart LR
    A["🟢 <b>Seasonal baseline</b><br/><br/>expected count + range<br/>disease × jurisdiction × week-of-year"] 
    B["🔵 <b>Nowcast</b><br/><br/>lag profile applied to recent weeks<br/>+ uncertainty band"]
    C["🟠 <b>Anomaly signals</b><br/><br/>score · fired flag · reason code<br/>corroboration count · earliness delta"]
    D["🟣 <b>Backtest eval</b><br/><br/>replays detection on<br/>point-in-time data"]

    A --> C
    B --> C
    C --> D
    C -->|"IS the payload"| E["📦 console + digest"]

    classDef m1 fill:#E7F5EE,stroke:#2A9D8F,stroke-width:2px,color:#14514A
    classDef m2 fill:#E8F4F8,stroke:#1F4E5F,stroke-width:2px,color:#1F4E5F
    classDef m3 fill:#FFF4E6,stroke:#F4A261,stroke-width:2px,color:#8A4B08
    classDef m4 fill:#F3E8FF,stroke:#8B5CF6,stroke-width:2px,color:#4C1D95
    classDef out fill:#E8EEFF,stroke:#4F43DD,stroke-width:2px,color:#2A2496

    class A m1
    class B m2
    class C m3
    class D m4
    class E out
```

---

## 🚦 Source tiering

> In an alerting system, a **bad source is worse than a missing one.**

```mermaid
flowchart TB
    T1["🟩 <b>TIER 1 — DRIVES ALERTS</b><br/>Federal APIs + official state/county/agency pages<br/><i>Crawled only where no API exists</i>"]
    T2["🟨 <b>TIER 2 — CORROBORATION, NEVER FIRES ALONE</b><br/>Advisory and recall event lane<br/><i>Raises or damps confidence on a Tier 1 signal — never originates one</i>"]
    T3["🟥 <b>TIER 3 — DELIBERATELY EXCLUDED</b><br/>News aggregators, unverified trackers<br/><i>Named in the README with the reason, not quietly omitted</i>"]

    T1 --> ALERT(["🔔 <b>ALERT FIRES</b>"])
    T2 -.->|"modulates<br/>confidence"| ALERT
    T3 -.->|"❌ blocked"| ALERT

    classDef t1 fill:#DCFCE7,stroke:#16A34A,stroke-width:2px,color:#14532D
    classDef t2 fill:#FEF9C3,stroke:#CA8A04,stroke-width:2px,color:#713F12
    classDef t3 fill:#FEE2E2,stroke:#DC2626,stroke-width:2px,color:#7F1D1D
    classDef al fill:#1F4E5F,stroke:#1F4E5F,stroke-width:2px,color:#FFFFFF

    class T1 t1
    class T2 t2
    class T3 t3
    class ALERT al
```

---

## 🧭 Architecture decisions

<details>
<summary><b>⚡ Batch where scheduled, stream only where arrival is irregular</b></summary>
<br>

The count feeds publish weekly, so streaming them would be theater — and the same logic applies to their deltas. The revision diff inherits the poll's schedule, so it runs as a batch job appending change records to an append-only revision log.

**Redpanda is carried by the event lane alone**, where arrival genuinely has no schedule. The honest framing, kept deliberately: the broker is on the résumé because the event lane needs it — not because streaming was applied wherever it could be.

</details>

<details>
<summary><b>📏 The event lane's existence is conditional on measured arrival rate</b></summary>
<br>

HAN alone is a handful of advisories a month, which a Dagster sensor would handle without a broker. The lane starts at 2–3 feeds and its existence is **decided by data before the first build weekend**: count the actual arrival rate of candidate feeds over a month.

If the combined rate supports bursty irregular arrival with real fan-out (corroboration mart, digest trigger), the broker is justified. If not, the lane drops to a Dagster sensor and the ADR records the measurement and the cut.

</details>

<details>
<summary><b>🚫 No LLM in the alerting path</b></summary>
<br>

An LLM classifier over FDA CORE investigation text was scoped and **removed**. FDA CORE is a Tier 1 source, and probabilistic classification on an alert-driving path is where non-determinism is least welcome. A deterministic extractor over a locked (disease, state, date-window) scope is more defensible.

**The consideration and the rejection are the deliverable here** — this ADR is the artifact, not an integration.

</details>

<details>
<summary><b>🔑 Snapshot-dated S3 keys, never overwrite</b></summary>
<br>

Keys carry the **pull date**, not just the reporting week, because CDC revises prior weeks as late cases arrive. Capturing those revisions over time is the raw material the nowcast learns the lag from.

Overwrite-on-rerun would destroy the exact signal the entire project depends on.

</details>

<details>
<summary><b>🕷️ Firecrawl only where data lives exclusively in pages — and the earliness is measured</b></summary>
<br>

All `data.cdc.gov` sources come through the Socrata API. Firecrawl is reserved for state/county pages and the FDA CORE table, which have no API. Crawling a clean Socrata API would be strictly worse and a reviewer would clock it instantly.

Every crawled item is **stamped with a first-seen timestamp**, and the backtest reports the delta against NNDSS first-appearance. A claim about tool fit that carries a number is worth more than the same claim asserted — and gives a defensible basis for cutting the lane if the number comes back near zero.

</details>

<details>
<summary><b>🧬 Disease-as-config from the first commit</b></summary>
<br>

Disease is a dimension carrying seasonality type, expected lag, and alert-eligibility — not hardcoded logic. Adding one is a config line plus a backfill, not new code.

Scoped to **2–3 diseases chosen for contrast, not coverage**: cyclosporiasis (seasonal, foodborne, long lag — the anchor) plus a low-count sporadic disease that tests robustness against small-sample false alarms.

</details>

<details>
<summary><b>📦 Frozen payload contract — console and digest are peers</b></summary>
<br>

The anomaly mart emits **one schema**, frozen before either consumer is built:

```json
{
  "disease": "cyclosporiasis",
  "jurisdictions": ["MI", "OH", "IN"],
  "score": 3.42,
  "fired": true,
  "reason_code": "BASELINE_EXCEEDED_SUSTAINED",
  "corroboration_count": 2,
  "earliness_delta_days": 9,
  "nowcast_band": { "point": 402, "low": 361, "high": 448 },
  "data_current_through": "2026-W27"
}
```

Both the console and the alert digest render this contract, which lets frontend work run **parallel to** detection instead of queueing behind it.

</details>

---

## ✂️ Scope discipline

Deliberately constrained, with the reasoning recorded rather than discovered later.

| ✅ In scope | ❌ Explicitly out |
|:---|:---|
| One baseline method + one lag model, explainable end to end | A survey of anomaly detection techniques |
| 2–3 diseases chosen for contrast | The full notifiable disease list |
| Corroboration as a scoped join on (disease, state, date window) | Fuzzy entity matching across sources |
| Console re-queries on load or light interval | Websocket/push updates for daily-moving data |
| Real "data current through week N" timestamp | Wall-clock render time masquerading as freshness |

---

## ⚠️ Known risks this plan owns

| Risk | Mitigation |
|:---|:---|
| 🎯 Backtest lead time is not under my control | Pre-registered success range + threshold sweep — a modest lead still ships as a credible artifact |
| 🕸️ Corroboration-join creep into entity resolution | Scope locked to (disease, state, date window); anything richer is explicitly out |
| 0️⃣ Off-season zero counts producing garbage scores | Verified against historical off-season data **before** the nowcast build starts |
| 📉 Earliness delta comes back near zero | Reportable finding, not a failure — becomes a cut-with-evidence decision |
| 📚 Streaming learning-curve tax | One brokered lane only, built after the arrival-rate check confirms it should exist |

---

## 📡 Data sources

> All public. All free. No API keys required for the core sources.

| Source | Provides | Lane |
|:---|:---|:---|
| **NNDSS weekly tables** `data.cdc.gov` | The spine — notifiable disease counts by state × week, provisional and revised as late cases arrive | 🔵 API + 🟢 Revision |
| **CDC CFA epidemic-trend (Rt)** | Model-ready respiratory signal; second detection pattern | 🔵 API |
| **FDA CORE outbreak table** | The leading edge, before a signal becomes a number in NNDSS | 🟠 Crawl |
| **CDC Health Alert Network** | Urgent advisories, genuinely event-shaped | 🔴 Event |
| **FDA / USDA FSIS recalls** | Product-level recalls; independent corroboration | 🔴 Event |
| **State / county dashboards** | Hotspot detail at county grain, ahead of federal aggregation | 🟠 Crawl |

---

## 🛑 Scope boundary

> [!WARNING]
> This is **early-warning risk monitoring on public data.** It is not food-safety certification and makes no regulatory or clinical claim. The system surfaces public signals faster; it does not adjudicate safety.

---

## 📁 Repository layout

```
📦 outbreak-monitoring-system
├── 📄 docs/
│   ├── decision-brief.pdf          # full project brief
│   ├── backtest.md                 # pre-registered criteria + results
│   └── adr/                        # architecture decision records
├── 🔌 ingestion/
│   ├── api/                        # Socrata extractors
│   ├── revision/                   # poll-over-poll batch diff
│   ├── crawl/                      # Firecrawl lane, first-seen stamped
│   └── events/                     # advisory/recall feeds → Redpanda
├── ⚙️ dbt/
│   └── models/
│       ├── staging/
│       ├── intermediate/           # harmonize · revision history · lag profile
│       └── marts/                  # baseline · nowcast · anomaly · backtest
├── 🧠 detection/                    # baseline, nowcast, scoring
├── 🎛️ orchestration/                # Dagster definitions
├── 🖥️ console/                      # React/Next.js
└── 🧬 config/
    └── diseases/                   # disease-as-config dimension
```

---

<div align="center">

**Portfolio capstone** · The client scenario in the decision brief is illustrative<br>
The backtest target is a real evaluation against the live 2026 cyclosporiasis outbreak

</div>
