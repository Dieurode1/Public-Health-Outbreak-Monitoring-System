# ADR 3 — Access method chosen per source, by what the source offers

**Status:** Accepted (2026-07-19)

## Decision

API where one exists; crawl only where data lives exclusively in pages.
Applied per source, not per lane.

## What verification changed

Two sources moved from their planned lane once measured:

**CDC HAN — event lane → crawl lane.** No live machine-readable feed exists.
`tools.cdc.gov/api/v2/resources/media/403372.rss` returns nothing;
`www2c.cdc.gov/podcasts/createrss.asp?c=177` parses but is abandoned — 124
entries, none after 2023-09-01, while CDC has continued issuing HANs through
2026 (HAN-00520 through HAN-00530). Reporting 0 items/30d from that feed would
report a dead pipe as a signal. HAN is ingested from its archive at
`cdc.gov/han/php/notices/index.html` instead: data living exclusively in pages
is precisely the crawl criterion. It remains a low-rate, high-severity
corroboration source, not a rate contributor.

**USDA FSIS — RSS → API.** FSIS publishes a public recall API carrying the full
archive with `field_states`, `field_recall_reason`, and
`field_related_to_outbreak` — the fields the corroboration join needs. The RSS
feed is strictly worse.

## Operational note

`fda.gov` and `fsis.usda.gov` return 403 to the default `requests` User-Agent.
All extractors go through `phoms.http.session()`.

## Consequence

The rule produces different answers for different sources, which is the
engineering signal. Firecrawl is reserved for HAN, FDA CORE, and state
dashboards — never for anything on data.cdc.gov.
