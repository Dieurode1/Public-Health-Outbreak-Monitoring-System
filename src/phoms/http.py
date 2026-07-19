"""Shared HTTP client.

fda.gov and fsis.usda.gov reject the default requests User-Agent with a 403,
so every extractor goes through here rather than setting headers ad hoc.
"""

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"


def session(retries: int = 3, backoff: float = 1.0) -> requests.Session:
    """Session with a browser UA and retry on transient failures."""
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    policy = Retry(
        total=retries,
        backoff_factor=backoff,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    s.mount("https://", HTTPAdapter(max_retries=policy))
    return s
