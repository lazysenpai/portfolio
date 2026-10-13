"""Data-hygiene checks that need no network, run before every ingest and in the tests.

  python3 hygiene.py                                      # configuration: map, profile, groups, segments
  python3 hygiene.py --fada fada.json --series DIR        # also reconcile FADA's months with Vahan

Configuration checks (blocking):
  map resolves      every Vahan maker resolves to exactly one ticker; no ticker is empty; every
                    ticker has an ISIN for its price and every maker a profile (an unprofiled maker
                    gets no segments and would silently read zero)
  groups classified every category group the source offers is in a segment or excluded with a reason,
                    so a group like Ambulance/Hearses can never again fall out unnoticed
  segment algebra   CV sits inside the four-wheeler block; single-group segments never touch it

FADA reconciliation (per ticker x segment x month, from fada.json and the series docs):
  within ±3%            agrees
  Vahan above, closed   late registrations (Telangana uploads to Vahan in batches, after FADA's cut): warning
  anything else         unexplained: blocking, unless listed in KNOWN with its reason

Exit: 0 clean, 2 a blocking finding, 1 the checks themselves failed.
"""
import argparse
import json
import os
import re
import sys
import traceback

from fetch_analytics import GROUPS
from ingest import Run, load_json
from segments import ALL6, BLOCK, CV, ORDER, SINGLE

ROOT = os.path.dirname(os.path.abspath(__file__))
EXCLUDED = {
    "Construction Equipment Vehicle": "earth movers and cranes; no FADA segment",
    "Public Service Vehicle": "a permit class that overlaps Bus and Four Wheeler (taxis); counting it would double-count",
    "Special Category Vehicles": "fire tenders, armoured and similar; no FADA segment",
    "Trailer": "trailers are not vehicle sales FADA counts",
}
AGREE = 0.03          # |Vahan / FADA - 1| within this agrees
LATE = 0.10           # a closed month may sit this far above FADA from late registrations before it is unexplained
KNOWN = {
    ("SMLMAH", "CV"): "Vahan's SML MAHINDRA LTD runs ~20% under FADA in every month checked (Sep 2025 too); "
                      "no other maker name (SML, ISUZU, S M L) closes it. Trend usable, level not.",
}
TICKER = re.compile(r"^[A-Z][A-Z0-9&-]{1,19}$")


def check_config(run, mapping, profile, isins):
    seen = {}
    for t, v in mapping["tickers"].items():
        run.check(bool(TICKER.match(t)), "map resolves", f"ticker {t!r} is not an NSE symbol")
        run.check(bool(v.get("makers")), "map resolves", f"{t} lists no makers")
        for n in v.get("makers", []):
            run.check(n not in seen, "map resolves", f"{n} maps to both {seen.get(n)} and {t}")
            seen[n] = t
        run.check(t in isins, "map resolves", f"{t} has no ISIN in isins.json, so no price")
    for n in seen:
        run.check(n in profile, "map resolves", f"{n} has no group profile in maker_groups.json: it would read zero")
    for g in GROUPS:
        inn, out = g in ALL6, g in EXCLUDED
        run.check(inn != out, "groups classified",
                  f"{g}: {'both used and excluded' if inn else 'neither in a segment nor excluded with a reason'}")
    run.check(set(CV) <= set(BLOCK), "segment algebra", "CV must sit inside the four-wheeler block")
    run.check(not ({g for v in SINGLE.values() for g in v} & set(BLOCK)), "segment algebra",
              "a single-group segment overlaps the four-wheeler block")
    run.check(set(SINGLE) | {"PV", "CV"} == set(ORDER), "segment algebra", "ORDER and the segment definitions differ")


def reconcile(run, fada, series, mapping):
    """[{ticker, seg, month, fada, vahan, diff, verdict}] for every FADA ticker row."""
    out = []
    months = fada["months"]
    latest = months[-1]
    for cat in fada["cats"]:
        seg = cat["k"]
        agg = {}
        for mk in cat["makers"]:
            if mk.get("sym"):
                a = agg.setdefault(mk["sym"], [0] * len(months))
                for i, v in enumerate(mk["v"]):
                    a[i] += v
        for sym, fv in agg.items():
            t = mapping["tickers"].get(sym)
            if not run.check(t is not None, "map resolves", f"FADA's {sym} is not a ticker in maker_map.json"):
                continue
            for i, m in enumerate(months):
                reg = (series.get(m[:4]) or {}).get("makers", {})
                vv = sum(((reg.get(n) or {}).get("segments", {}).get(seg) or {}).get(m, 0) for n in t["makers"])
                f = fv[i]
                diff = vv / f - 1 if f else 0.0
                if abs(diff) <= AGREE:
                    verdict = "agrees"
                elif (sym, seg) in KNOWN:
                    verdict = "known: " + KNOWN[(sym, seg)]
                elif 0 < diff <= LATE and m != latest:
                    verdict = "late registrations"
                else:
                    verdict = "unexplained"
                out.append({"ticker": sym, "seg": seg, "month": m, "fada": f, "vahan": vv, "diff": round(diff, 4), "verdict": verdict})
                if verdict == "late registrations":
                    run.check(False, "FADA reconciles", f"{sym} {seg} {m}: Vahan {diff:+.1%} over FADA, late registrations", blocking=False)
                elif verdict == "unexplained":
                    run.check(False, "FADA reconciles", f"{sym} {seg} {m}: Vahan {vv:,} vs FADA {f:,} ({diff:+.1%})")
                else:
                    run.check(True, "FADA reconciles", "")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fada", help="FADA's maker table (the dashboard's AUTO object), JSON")
    ap.add_argument("--series", help="dir holding series-YYYY.json docs (ArtifactData out_dir/vahan or seed output)")
    ap.add_argument("--report", help="write the reconciliation rows here, JSON")
    a = ap.parse_args()
    mapping = load_json(os.path.join(ROOT, "maker_map.json"))
    profile = load_json(os.path.join(ROOT, "maker_groups.json"))["groups"]
    isins = load_json(os.path.join(ROOT, "isins.json"))["isin"]
    run = Run()
    check_config(run, mapping, profile, isins)
    rows = []
    if a.fada and a.series:
        fada = load_json(a.fada)
        series = {}
        for y in {m[:4] for m in fada["months"]}:
            doc = load_json(os.path.join(a.series, f"series-{y}.json"))
            run.check(doc is not None, "FADA reconciles", f"no series-{y}.json in {a.series}")
            if doc:
                series[y] = doc["reg"]
        rows = reconcile(run, fada, series, mapping)
        if a.report:
            json.dump(rows, open(a.report, "w"), indent=1)
    summary = {"ok": not run.blockers, "passed": len(run.passed), "blockers": run.blockers, "warnings": len(run.warnings)}
    if rows:
        summary["fada"] = {v: sum(1 for r in rows if r["verdict"].split(":")[0] == v) for v in ("agrees", "late registrations", "known", "unexplained")}
    print(json.dumps(summary, indent=1))
    return 0 if not run.blockers else 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
