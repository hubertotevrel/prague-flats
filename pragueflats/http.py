"""Shared HTTP session — the foundation chosen in step 1: a browser-like requests
Session with transparent retries/backoff (stdlib urllib gets reset by iDnes)."""
import requests
from requests.adapters import HTTPAdapter

try:
    from urllib3.util.retry import Retry
except Exception:  # pragma: no cover
    Retry = None

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "Accept-Language": "cs,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    if Retry is not None:
        retry = Retry(total=4, backoff_factor=0.6,
                      status_forcelist=[429, 500, 502, 503, 504],
                      allowed_methods=["GET", "POST"])
        s.mount("https://", HTTPAdapter(max_retries=retry))
    return s
