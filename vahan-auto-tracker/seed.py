"""Seed the dashboard's database from the stored backfill, as files plus a writes.json for
ArtifactData batch — the same shape ingest.py emits, so the first daily run picks up from it.

  python3 seed.py --out <dir>
"""
import argparse
import csv
import glob
import hashlib
import io
import json
import os
import zipfile
from datetime import datetime, timezone

from assemble import year
from ingest import Run, check_year

ROOT = os.path.dirname(os.path.abspath(__file__))
YEARS = [2024, 2025, 2026]


def bhav_rows(path):
    with zipfile.ZipFile(path) as z:
        return list(csv.DictReader(io.TextIOWrapper(z.open(z.namelist()[0]), encoding="utf-8")))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--latest-bhav", help="a later bhavcopy zip to include (e.g. the day before the first run)")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    writes = []

    def emit(doc_id, doc):
        p = os.path.join(a.out, f"{doc_id}.json")
        json.dump(doc, open(p, "w"), separators=(",", ":"))
        writes.append({"op": "set", "collection": "vahan", "doc_id": doc_id, "file_path": os.path.abspath(p)})
        return os.path.getsize(p)

    mapping = json.load(open(os.path.join(ROOT, "maker_map.json")))
    isins = json.load(open(os.path.join(ROOT, "isins.json")))["isin"]
    baseline = json.load(open(os.path.join(ROOT, "maker_groups.json"))).get("otherBaseline", {})

    # registrations, checked by the same code the daily run uses
    run, stamps, sizes = Run(), [], {}
    regs = {}
    for y in YEARS:
        reg, lo, hi = year(y)
        check_year(run, y, reg, None, "2026-10", baseline)
        regs[y] = reg
        stamps += [lo, hi]
    if run.blockers:
        raise SystemExit(f"backfill fails its own checks: {run.blockers[:3]}")
    as_of = max(stamps)
    for y in YEARS:
        sizes[f"series-{y}"] = emit(f"series-{y}", {"year": y, "readAt": as_of, "reg": regs[y]})

    # prices: month-end closes from the archive, plus any later file given
    files = sorted(glob.glob(os.path.join(ROOT, "data", "bhav", "udiff_*.zip")))
    if a.latest_bhav:
        files.append(a.latest_bhav)
    by_year = {}
    for f in files:
        rows = bhav_rows(f)
        by_isin = {r["ISIN"]: r for r in rows if r["SctySrs"] in ("EQ", "BE")}
        day = rows[0]["TradDt"]
        closes = {t: float(by_isin[i]["ClsPric"]) for t, i in isins.items() if i in by_isin}
        doc = by_year.setdefault(day[:4], {"year": day[:4], "closes": {}, "bhavSha256": {},
                                           "note": "Month-end closes only before the first daily run."})
        doc["closes"][day] = closes
        doc["bhavSha256"][day] = hashlib.sha256(open(f, "rb").read()).hexdigest()
    prices_to = max(d for v in by_year.values() for d in v["closes"])
    for y, doc in by_year.items():
        sizes[f"prices-{y}"] = emit(f"prices-{y}", doc)

    emit("held", {"items": [
        {"ticker": "TMPV", "date": "2025-10-14", "from": 660.75, "to": 395.45, "confirmed": False,
         "note": "Demerger of the commercial-vehicle business, ex-date 14 Oct 2025 (660.75 → 395.45). "
                 "Before this the price is the whole of Tata Motors, PV and CV together."},
        {"ticker": "ASHOKLEY", "date": "2025-07-16", "from": 250.90, "to": 124.60, "confirmed": False,
         "note": "Price halved overnight on 16 Jul 2025 (250.90 → 124.60), consistent with a 1:1 bonus. Not yet confirmed."},
    ]})

    # this month's first reading, from the same fetch
    cur = "2026-10"
    r26 = regs[2026]
    emit(f"daily-{cur}", {"month": cur, "readings": [{
        "readAt": as_of, "date": as_of[:10], "source": "backfill",
        "market": r26["market"]["total"].get(cur),
        "marketSegments": {k: v.get(cur) for k, v in r26["market"]["segments"].items()},
        "makers": {n: {"total": m["total"].get(cur), "segments": {k: v.get(cur) for k, v in m["segments"].items()}}
                   for n, m in r26["makers"].items()}}]})

    emit("map", mapping)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    status = {"run": "seed", "ranAt": now, "ok": True, "blockers": [], "warnings": run.warnings,
              "checksPassed": len(run.passed), "checksTotal": len(run.passed) + len(run.warnings),
              "lastGood": now, "dataAsOf": as_of, "pricesTo": prices_to,
              "source": "Seeded from the Jan 2024 – Oct 2026 backfill of the Parivahan analytics dashboard and NSE month-end bhavcopies."}
    emit("status", status)
    emit(f"runs-{cur}", {"items": [{"run": "seed", "ranAt": now, "ok": True, "checksPassed": status["checksPassed"],
                                     "checksTotal": status["checksTotal"], "blockers": [], "warnings": len(run.warnings),
                                     "note": "seeded from backfill"}]})
    json.dump(writes, open(os.path.join(a.out, "writes.json"), "w"), indent=1)
    print(json.dumps({"docs": len(writes), "dataAsOf": as_of, "pricesTo": prices_to,
                      "checks": f"{status['checksPassed']}/{status['checksTotal']}", "largest": max(sizes.items(), key=lambda kv: kv[1])}))


if __name__ == "__main__":
    main()
