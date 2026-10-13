"""Assemble stored analytics responses into the same per-year structure ingest.py builds,
so the backfill can be checked by the same code and used to seed the database.

  python3 assemble.py check 2024 2025 2026     # run ingest's checks over the stored history
  python3 assemble.py baseline 2025            # each maker's usual share outside its segments
"""
import json
import os
import sys

from backfill_analytics import path_for, makers
from ingest import Run, check_year

ROOT = os.path.dirname(os.path.abspath(__file__))


def year(y):
    from segments import ORDER, build, key, requests_for, segments_of
    prof = json.load(open(os.path.join(ROOT, "maker_groups.json")))["groups"]
    stamps = []

    def one(maker, segs):
        got = {}
        for g in requests_for(segs):
            rec = json.load(open(path_for(y, maker, g)))
            got[key(g)] = rec["months"]
            stamps.append(rec["fetched_at"])
        return build(got, segs)

    out = {"market": one(None, ORDER),
           "makers": {n: one(n, segments_of(prof.get(n, []))) for _, n in makers()}}
    return out, min(stamps), max(stamps)


def baseline(y):
    """Share of a maker's year outside its segments, from deduplicated segments."""
    reg, _, _ = year(y)
    out = {}
    for n, b in reg["makers"].items():
        total = sum(b["total"].values())
        covered = sum(b["covered"].values())
        out[n] = round(1 - covered / total, 4) if total else 0
    p = os.path.join(ROOT, "maker_groups.json")
    prof = json.load(open(p))
    prof["otherBaseline"] = out
    prof["otherBaselineFrom"] = f"{y}, deduplicated segments"
    json.dump(prof, open(p, "w"), indent=1)
    for n, v in sorted(out.items(), key=lambda kv: -kv[1])[:8]:
        print(f"  {v:6.1%}  {n}")


if __name__ == "__main__":
    mode, years = sys.argv[1], [int(y) for y in sys.argv[2:]]
    if mode == "baseline":
        baseline(years[0])
        raise SystemExit
    baseline = json.load(open(os.path.join(ROOT, "maker_groups.json"))).get("otherBaseline", {})
    for y in years:
        reg, lo, hi = year(y)
        r = Run()
        check_year(r, y, reg, None, "2026-10", baseline)
        print(f"{y}: fetched {lo} .. {hi}; {len(r.passed)} passed, {len(r.blockers)} blockers, {len(r.warnings)} warnings")
        for b in r.blockers[:8]:
            print("   BLOCK", b["detail"])
        for w in r.warnings[:12]:
            print("   warn ", w["detail"])
