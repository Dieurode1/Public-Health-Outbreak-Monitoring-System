# ADR 10 — Michigan is a PDF-extraction source, not a crawl target

**Status:** Accepted (2026-07-19)

## Gate 3 result

The brief asked whether the chosen state's data genuinely requires crawling.
Answer: neither candidate is a crawl target, for different reasons.

**Ohio — disqualified.** The DataOhio "Summary of Infectious Diseases in Ohio"
dashboard states that viewing the data requires an account, login, and access
approval. Authentication puts it outside both the API and crawl lanes.
(Determined from ODH/DataOhio published descriptions, not from an
authenticated session — revisit if the access model changes.)

**Michigan — selected, but as PDF extraction.** MDHHS publishes a Weekly Disease
Report as a PDF at `.../CDINFO/WSR/WSR-{WW}-{YYYY}.pdf` (week zero-padded —
verified: `WSR-03-2026.pdf` returns 200, `WSR-3-2026.pdf` returns 404). This is a third access
category the brief did not anticipate: not an API, not a page to crawl, but a
document to parse. Firecrawl is the wrong tool; `pdfplumber` is the right one.

## Why Michigan is worth the parsing cost

- **County grain** — 83 counties plus Detroit City, a level below NNDSS's state grain
- **MMWR week labels** — joins to NNDSS on `(year, week)` directly
- **Independent confirmation of the revision premise** — the report states MDSS
  counts change constantly as cases are investigated, confirmed, or ruled out
- **Backfillable** — the dated URL pattern means historical revision behavior can
  be reconstructed now rather than accumulated over months

## Consequence

Firecrawl's only remaining justified target is CDC HAN (see ADR 3). The crawl
lane is one source, which is the honest scope.

`Current_WSR.pdf` is a rolling URL and must never be the ingestion path — it
overwrites weekly. Ingest by dated URL, snapshot on arrival per ADR 5.
