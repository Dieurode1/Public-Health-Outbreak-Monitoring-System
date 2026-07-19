"""ADR 2 gate — event-lane arrival rate over the trailing 30 days.

Sources measured as they are actually accessible:
  FDA recalls  — RSS (truncated at 20 items; count is a floor)
  FSIS         — public API, full archive, state-level
  CDC outbreaks— RSS
  CDC HAN      — no working feed found; reclassified to crawl lane (ADR 3)
"""
import datetime
from collections import Counter

import feedparser
import requests

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
WINDOW = 30
cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=WINDOW)
counts = Counter()

RSS = {
    "fda_recalls": "https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/recalls/rss.xml",
    "cdc_outbreaks": "https://tools.cdc.gov/api/v2/resources/media/285676.rss",
}

for name, url in RSS.items():
    feed = feedparser.parse(url, request_headers=UA)
    recent, oldest = 0, None
    for e in feed.entries:
        st = e.get("published_parsed") or e.get("updated_parsed")
        if not st:
            continue
        dt = datetime.datetime(*st[:6], tzinfo=datetime.timezone.utc)
        oldest = min(oldest, dt) if oldest else dt
        if dt >= cutoff:
            recent += 1
    counts[name] = recent
    truncated = " TRUNCATED-floor" if oldest and oldest >= cutoff else ""
    print(f"{name:<16} {recent:>3}/30d ({recent/WINDOW*7:.1f}/wk) [{len(feed.entries)} in feed]{truncated}")

data = requests.get("https://www.fsis.usda.gov/fsis/api/recall/v/1", headers=UA, timeout=60).json()
iso = cutoff.date().isoformat()
recent = [r for r in data if (r.get("field_recall_date") or "") >= iso]
counts["fsis_api"] = len(recent)
print(f"{'fsis_api':<16} {len(recent):>3}/30d ({len(recent)/WINDOW*7:.1f}/wk) [{len(data)} total records]")

total = sum(counts.values())
print(f"\nCOMBINED: {total}/30d = {total/WINDOW*7:.1f} items/week")
print("Gate: >= ~3/wk supports the broker.")
print("NOTE: FDA count is a floor (feed truncates). HAN excluded — no feed; crawl lane per ADR 3.")
