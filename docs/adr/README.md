# Architecture Decision Records

| ADR | Decision | Status |
|---|---|---|
| 001 | Batch where scheduled, stream only where arrival is irregular | Brief |
| [002](002-event-lane.md) | Event lane conditional on measured arrival rate | Accepted — 4.9/wk |
| [003](003-access-method-per-source.md) | Access method per source; HAN→crawl, FSIS→API | Accepted |
| 004 | No LLM in the alerting path | Brief |
| [005](005-snapshot-keys.md) | Snapshot-dated keys, never overwrite | Accepted |
| 006 | Multi-disease by design, disease-as-config | Brief |
| 007 | Frozen payload contract; console and digest are peers | Brief |
| [008](008-jurisdiction-grain.md) | Jurisdiction grain explicit; only states alert | Accepted |
| [009](009-measure-type.md) | Counts carry measure_type; no cross-type comparison | Accepted |
| [010](010-michigan-pdf-extraction.md) | Michigan is PDF extraction; Ohio disqualified (auth) | Accepted |

ADRs 001, 004, 006, 007 are carried from the decision brief and written up as
their implementations land. 002, 003, 005, 008, 009, 010 are backed by
measurement or by what verification found in the sources themselves.
