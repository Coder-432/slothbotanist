"""Weekly per-herb safety scan.

Runs one google_news search per herb on a watchlist, caches every response, and prints a
quantified headline ("N of M news listings across K herbs carry a safety signal").
429s are never retried: the herb is recorded as rate_limited and the scan moves on.

Usage:
  SERPAPI_KEY=... python weekly_scan.py ginger turmeric elderberry
Schedule weekly with cron, e.g.:  0 7 * * 1  cd /path && python weekly_scan.py ginger turmeric
"""
import json
import os
import sys
import time
from datetime import date

from serpapi import Client

from apothecary_core import (
    DiskCache, extract_sources, dedupe_sources, is_param_rejection, is_rate_limit,
    weekly_scan_summary,
)

SASL = os.getenv("SERPAPI_SASL", "1") == "1"


def scan(herbs, client, cache):
    per_herb, skipped = {}, {}
    for herb in herbs:
        params = {"engine": "google_news", "q": f"{herb} herbal safety interaction recall"}
        if SASL:
            params |= {"_sasl": 1, "_saslop": 1}
        cached = cache.get("google_news", params)
        try:
            try:
                data = dict(client.search(params))
                if "error" in data:
                    raise RuntimeError(str(data["error"]))
            except Exception as e:  # noqa: BLE001
                if not (SASL and is_param_rejection(str(e))):
                    raise
                params.pop("_sasl"), params.pop("_saslop")  # single retry, flags only
                data = dict(client.search(params))
                if "error" in data:
                    raise RuntimeError(str(data["error"]))
            cache.put("google_news", params, data)
        except Exception as e:  # noqa: BLE001
            if cached:
                data = cached
                skipped[herb] = "used_cache_after_error"
            else:
                skipped[herb] = "rate_limited" if is_rate_limit(str(e)) else f"error: {e}"
                continue
        per_herb[herb] = dedupe_sources(extract_sources("google_news", data, limit=10))
        time.sleep(0.5)
    summary = weekly_scan_summary(per_herb)
    summary["skipped"] = skipped
    summary["date"] = date.today().isoformat()
    return summary


if __name__ == "__main__":
    herbs = sys.argv[1:]
    if not herbs or not os.getenv("SERPAPI_KEY"):
        sys.exit("usage: SERPAPI_KEY=... python weekly_scan.py herb [herb ...]")
    report = scan(herbs, Client(api_key=os.environ["SERPAPI_KEY"]), DiskCache())
    out = f"weekly_report_{report['date']}.json"
    with open(out, "w") as f:
        json.dump(report, f, indent=2)
    print(report["headline"])
    print(f"Saved {out}; skipped: {report['skipped'] or 'none'}")
