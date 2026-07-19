"""
Pre-build verification #2 — event-lane arrival rate (ADR 2 gate).

WHY THIS EXISTS
---------------
ADR 2 makes the event lane's existence conditional on measurement, not on
wanting a broker on the resume. The rule: if the candidate feeds combined
deliver a few items a week or more, bursty irregular arrival plus fan-out to
real consumers (corroboration mart, digest trigger) justifies Redpanda. Below
that, the lane collapses to a Dagster sensor and the ADR records the cut.
This script produces the number that decides it.

WHAT IT DOES
------------
Counts items published in the trailing 30 days across the candidate Tier 2
sources, reports each source's rate and the combined weekly rate, and flags
feeds whose oldest entry falls inside the window (meaning the feed is truncated
and the count is a floor, not a measurement).

    python -m phoms.extract.verify_arrival_rate

FINDINGS (2026-07-19) — GATE PASSES AT 4.9 items/week
-----------------------------------------------------
  fda_recalls    3.5/wk  RSS, truncated at 20 items -> count is a FLOOR
  cdc_outbreaks  0.5/wk  RSS
  fsis_api       0.9/wk  true rate, measured against full 2,011-record archive
  ------------------------------------------------
  COMBINED       4.9/wk  (lower bound)

The lane is carried by FDA recalls. FSIS is small but exact. Combined rate
clears the bar without HAN contributing anything.

SOURCE DECISIONS THIS MEASUREMENT FORCED
----------------------------------------
  * CDC HAN — no working machine-readable feed exists. tools.cdc.gov/.../403372
    returns nothing; www2c.cdc.gov/podcasts/createrss.asp?c=177 parses but is
    ABANDONED (124 entries, none after 2023-09-01) while CDC has continued
    issuing HANs through 2026. Reporting 0/30d from that feed would be reporting
    a dead pipe as a signal. HAN therefore moves OUT of the event lane and INTO
    the crawl lane (archive at cdc.gov/han/php/notices/index.html) — which is
    exactly ADR 3's criterion: crawl only where data lives exclusively in pages.
    It remains a low-rate, high-severity corroboration source, not a rate
    contributor.
  * USDA FSIS — the RSS feed is thin, but FSIS publishes a public recall API
    (launched 2023) carrying the full archive with field_states,
    field_recall_reason, and field_related_to_outbreak. Per ADR 3 (API where one
    exists), FSIS is ingested via API. Those fields map directly onto the
    corroboration mart's (disease, state, date-window) scoped join.
  * User-agent — fda.gov and fsis.usda.gov both 403 the default python-requests
    UA. Every extractor needs a browser UA. This belongs in a shared HTTP client
    in phoms.extract, not repeated per script.

HONEST CAVEAT FOR THE ADR
-------------------------
4.9/wk is a lower bound from a single 30-day window. The FDA component is
truncated and one source dominates the total. If FDA recalls were removed, the
lane would not clear. Worth stating plainly rather than presenting 4.9 as a
clean measurement.
"""
import datetime
from collections import Counter

import feedparser
import requests

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
WINDOW = 30
FSIS_API = "https://www.fsis.usda.gov/fsis/api/recall/v/1"
RSS = {
    "fda_recalls": "https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/recalls/rss.xml",
    "cdc_outbreaks": "https://tools.cdc.gov/api/v2/resources/media/285676.rss",
}


def main():
    cutoff = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=WINDOW)
    counts = Counter()

    for name, url in RSS.items():
        feed = feedparser.parse(url, request_headers=UA)
        recent, oldest = 0, None
        for e in feed.entries:
            st = e.get("published_parsed") or e.get("updated_parsed")
            if not st:
                continue
            dt = datetime.datetime(*st[:6], tzinfo=datetime.UTC)
            oldest = min(oldest, dt) if oldest else dt
            if dt >= cutoff:
                recent += 1
        counts[name] = recent
        floor = " TRUNCATED-floor" if oldest and oldest >= cutoff else ""
        print(f"{name:<16} {recent:>3}/30d ({recent / WINDOW * 7:.1f}/wk) "
              f"[{len(feed.entries)} in feed]{floor}")

    data = requests.get(FSIS_API, headers=UA, timeout=60).json()
    iso = cutoff.date().isoformat()
    recent = [r for r in data if (r.get("field_recall_date") or "") >= iso]
    counts["fsis_api"] = len(recent)
    print(f"{'fsis_api':<16} {len(recent):>3}/30d ({len(recent) / WINDOW * 7:.1f}/wk) "
          f"[{len(data)} total records]")

    total = sum(counts.values())
    print(f"\nCOMBINED: {total}/30d = {total / WINDOW * 7:.1f} items/week")
    print("Gate: >= ~3/wk supports the broker (ADR 2).")
    print("NOTE: FDA count is a floor. HAN excluded — no feed; crawl lane per ADR 3.")


if __name__ == "__main__":
    main()
