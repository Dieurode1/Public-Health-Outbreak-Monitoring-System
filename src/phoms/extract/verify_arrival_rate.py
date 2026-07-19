"""
Verification script — do the advisory feeds arrive often enough to need a broker?

The event lane carries Tier 2 corroboration sources: public advisories and
recalls that raise or damp confidence in an anomaly but never fire an alert
alone. Measured here:

  FDA recalls    — RSS. Food and drug recall notices, all product categories.
  CDC outbreaks  — RSS. Multistate foodborne outbreak investigations.
  USDA FSIS      — API. Meat/poultry recalls and public health alerts;
                   independent of FDA, so it corroborates rather than echoes.

ADR 2 makes the broker conditional on measurement: >= ~3 items/week justifies
Redpanda, below that the lane drops to a Dagster sensor. This produces the number.

    python -m phoms.extract.verify_arrival_rate

Result 2026-07-19: 4.9/wk — passes. Lower bound; FDA's feed truncates at 20
items so its count is a floor, and FDA alone carries most of the total.

Source notes:
  HAN (CDC's urgent clinician advisories) has no live feed — the tools.cdc.gov
  one is dead since 2023 while CDC keeps publishing. Excluded here, ingested via
  crawl lane instead (ADR 3).
  FSIS uses its recall API, not RSS: full archive plus field_states and
  field_related_to_outbreak, which the corroboration join needs.
  fda.gov and fsis.usda.gov 403 the default requests UA. Browser UA required.

See docs/adr/002-event-lane.md.
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


if __name__ == "__main__":
    main()
