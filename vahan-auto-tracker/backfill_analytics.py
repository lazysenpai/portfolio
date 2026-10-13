"""One-time backfill from the Parivahan analytics dashboard, resumable.

Every response is stored untouched under data/analytics/<year>/<key>.json with its
SHA-256 and fetch time, so a rerun skips what it already has and nothing is ever
overwritten in place.

  python3 backfill_analytics.py profile 2025     # every mapped maker x every main group
  python3 backfill_analytics.py history 2024 2025 2026   # totals + each maker's own groups
"""
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

import requests

from fetch_analytics import fetch, params, URL, UA, to_months

ROOT = os.path.dirname(os.path.abspath(__file__))
STORE = os.path.join(ROOT, "data", "analytics")
MAIN_GROUPS = ["Two Wheeler", "Three Wheeler", "Four Wheeler", "Goods Vehicle", "Bus", "Tractor"]
PAUSE = 1.0                                  # seconds between requests: be a light visitor


def slug(s):
    return re.sub(r"[^A-Za-z0-9]+", "_", s or "ALL").strip("_")[:80]


def path_for(year, maker, group):
    g = "+".join(group) if isinstance(group, list) else group
    return os.path.join(STORE, str(year), f"{slug(maker)}__{slug(g)}.json")


def get(year, maker, group, session):
    p = path_for(year, maker, group)
    if os.path.exists(p):
        return json.load(open(p))["months"], False
    r = session.get(URL, params=params(year, maker, group), timeout=60,
                    headers={"User-Agent": UA, "X-Requested-With": "XMLHttpRequest"})
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code} for {maker} {group} {year}")
    months = to_months(r.json(), year)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    rec = {"year": year, "maker": maker, "group": group,
           "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "sha256": hashlib.sha256(r.content).hexdigest(), "raw": r.json(), "months": months}
    tmp = p + ".tmp"
    json.dump(rec, open(tmp, "w"))
    os.replace(tmp, p)                       # atomic: a half-written file never exists
    return months, True


def makers():
    m = json.load(open(os.path.join(ROOT, "maker_map.json")))["tickers"]
    return [(t, n) for t, v in m.items() for n in v["makers"]]


def run(jobs):
    s = requests.Session()
    done = fetched = 0
    for year, maker, group in jobs:
        try:
            _, new = get(year, maker, group, s)
        except Exception as e:
            print(f"FAIL {year} {maker} {group}: {e}", flush=True)
            continue
        done += 1
        if new:
            fetched += 1
            time.sleep(PAUSE)
        if done % 25 == 0:
            print(f"{done}/{len(jobs)} ({fetched} fetched)", flush=True)
    print(f"done {done}/{len(jobs)}, fetched {fetched}", flush=True)


if __name__ == "__main__":
    mode, years = sys.argv[1], [int(y) for y in sys.argv[2:]]
    if mode == "profile":
        jobs = [(y, n, g) for y in years for _, n in makers() for g in [None] + MAIN_GROUPS]
    elif mode == "history":
        from segments import segments_of, requests_for, ORDER
        prof = json.load(open(os.path.join(ROOT, "maker_groups.json")))["groups"]
        jobs = [(y, None, g) for y in years for g in requests_for(ORDER)]
        jobs += [(y, n, g) for y in years for _, n in makers() for g in requests_for(segments_of(prof.get(n, [])))]
    else:
        raise SystemExit("mode is profile or history")
    run(jobs)
