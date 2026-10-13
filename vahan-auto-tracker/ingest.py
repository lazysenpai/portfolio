"""Daily ingest: Parivahan analytics registrations + NSE closes -> checked database writes.

The routine's agent does three mechanical things around this script and nothing else:
  1. ArtifactData list  collection "vahan"  out_dir=<state dir>     (yesterday's state, as files)
  2. python3 ingest.py --state <state dir>/vahan --out <out dir>
  3. if exit code is 0 or 2: ArtifactData batch with the entries in <out dir>/writes.json
The script decides everything: what was fetched, whether it passes, what to write.

Exit codes
  0  data passed every blocking check; writes.json holds data docs + status
  2  a blocking check failed; writes.json holds the status doc only (data untouched)
  3  the source has not posted today's figures yet; nothing to write, run again later
  1  the script itself failed; nothing to write
"""
import argparse
import hashlib
import json
import os
import sys
import time
import traceback
from datetime import date, datetime, timedelta, timezone

import requests

from fetch_analytics import fetch, SourceError
from segments import ORDER, build, key, requests_for, segments_of
import weekly

ROOT = os.path.dirname(os.path.abspath(__file__))
IST = timezone(timedelta(hours=5, minutes=30))
PAUSE = 1.0
PRICE_JUMP = 0.20          # an overnight move beyond this is held as a possible corporate action
MTD_DIP = 0.005            # a month-to-date count may fall this much (cancellations) before it blocks
CLOSED_MOVE = 0.005        # a closed month's market total may move this much in a day before it blocks
OTHER_SHARE = 0.03         # rise in a maker's share outside its segments, over its baseline, before a warning
DEADLINE = 8 * 60          # seconds: stop, blocked, rather than hang; under the routine shell's 10-minute limit


def now_ist():
    return datetime.now(IST)


def load_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return default


class Run:
    def __init__(self):
        self.blockers, self.warnings, self.passed = [], [], []

    def check(self, ok, name, detail, blocking=True):
        if ok:
            self.passed.append(name)
        elif blocking:
            self.blockers.append({"check": name, "detail": detail})
        else:
            self.warnings.append({"check": name, "detail": detail})
        return ok


# ---------------------------------------------------------------- fetch

def fetch_registrations(years, makers, profile):
    """{year: {"market": built, "makers": {name: built}}}, built = segments.build(...)"""
    s = requests.Session()
    out = {}
    stop = time.monotonic() + DEADLINE

    def one(y, maker, segs):
        got = {}
        for groups in requests_for(segs):
            if time.monotonic() > stop:
                raise SourceError(f"fetching took over {DEADLINE // 60} minutes; stopped at {maker or 'market'} {y}")
            got[key(groups)] = fetch(y, maker=maker, group=groups, session=s)
            time.sleep(PAUSE)
        return build(got, segs)

    for y in years:
        out[y] = {"market": one(y, None, ORDER),
                  "makers": {n: one(y, n, segments_of(profile.get(n, []))) for n in makers}}
    return out


def fetch_prices(isins, today):
    """Latest NSE bhavcopy strictly before today: (trade_date, {ticker: close}, sha256)."""
    import csv, io, zipfile
    url = "https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{d}_F_0000.csv.zip"
    ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128 Safari/537.36"
    d = today - timedelta(days=1)
    for _ in range(7):
        if d.weekday() < 5:
            r = requests.get(url.format(d=d.strftime("%Y%m%d")), headers={"User-Agent": ua}, timeout=60)
            if r.status_code == 200 and r.content[:2] == b"PK":
                with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                    rows = list(csv.DictReader(io.TextIOWrapper(z.open(z.namelist()[0]), encoding="utf-8")))
                by_isin = {x["ISIN"]: x for x in rows if x["SctySrs"] in ("EQ", "BE")}
                closes = {t: float(by_isin[i]["ClsPric"]) for t, i in isins.items() if i in by_isin}
                return d.isoformat(), closes, hashlib.sha256(r.content).hexdigest()
        d -= timedelta(days=1)
    raise SourceError("no NSE bhavcopy in the last 7 days")


# ---------------------------------------------------------------- checks

def slack(key, cur_month, n):
    """Requests in one run are seconds apart; a live month may move between them."""
    return max(5, int(n * 0.005)) if key == cur_month else max(2, int(n * 0.001))


def check_built(run, who, b, cur_month, usual=None):
    segs = b["segments"]
    for key, total in b["total"].items():
        vals = {k: v.get(key, 0) for k, v in segs.items()}
        neg = {k: x for k, x in vals.items() if x < 0}
        if not run.check(not neg, "segments never negative", f"{who} {key}: {neg}"):
            continue
        ssum = sum(vals.values())
        run.check(ssum <= total + slack(key, cur_month, total), "segments within total",
                  f"{who} {key}: segments sum to {ssum:,}, total is {total:,}")
        if "own" in b:
            u = b["own"].get(key, 0)
            run.check(abs(ssum - u) <= slack(key, cur_month, u), "no vehicle counted twice",
                      f"{who} {key}: segments sum to {ssum:,}, the union of their groups is {u:,}")
        if usual is not None and key != cur_month and total >= 1000:
            other = (total - b["covered"].get(key, 0)) / total
            run.check(other <= usual + OTHER_SHARE, "maker outside its usual segments",
                      f"{who} {key}: {other:.1%} of registrations fall outside {', '.join(segs)} (usually {usual:.1%})",
                      blocking=False)


def check_year(run, y, cur, prev, cur_month, baseline=None):
    """cur/prev: one year's registrations today and as stored yesterday (prev may be None)."""
    check_built(run, "market", cur["market"], cur_month)
    for n, b in cur["makers"].items():
        check_built(run, n, b, cur_month, (baseline or {}).get(n, 0))
    if not prev:
        return []
    revisions = []
    for key, total in cur["market"]["total"].items():
        old = prev["market"]["total"].get(key)
        if old is None or key == cur_month:
            continue
        move = (total - old) / old if old else 0
        # Late registrations only ever add (Telangana uploads its months to Vahan in batches), so a
        # closed month that grows is a revision, logged and shown; one that shrinks is suspect and blocks.
        run.check(move >= -CLOSED_MOVE, "closed months never shrink",
                  f"market total for {key} fell {move:+.2%} overnight ({old:,} -> {total:,})")
        run.check(move <= CLOSED_MOVE, "closed months stable",
                  f"market total for {key} grew {move:+.2%} overnight ({old:,} -> {total:,}): late registrations",
                  blocking=False)
    for n, b in cur["makers"].items():
        pm = prev["makers"].get(n)
        if not pm:
            continue
        for key, total in b["total"].items():
            old = pm["total"].get(key)
            if old is None or old == total:
                continue
            if key == cur_month:
                run.check(total >= old * (1 - MTD_DIP), "month to date never shrinks",
                          f"{n} {key}: {old:,} yesterday, {total:,} today")
            else:
                revisions.append({"maker": n, "month": key, "from": old, "to": total})
    return revisions


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", required=True, help="dir of yesterday's docs (ArtifactData out_dir/vahan)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--today", help="YYYY-MM-DD, for tests")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    t = now_ist()
    today = date.fromisoformat(a.today) if a.today else t.date()
    run_id = t.strftime("%Y%m%dT%H%M%S")
    cur_month = today.strftime("%Y-%m")
    years = [today.year - 1, today.year] if today.month == 1 else [today.year]

    mapping = load_json(os.path.join(ROOT, "maker_map.json"))
    prof = load_json(os.path.join(ROOT, "maker_groups.json"))
    profile, baseline = prof["groups"], prof.get("otherBaseline", {})
    makers = sorted({n for v in mapping["tickers"].values() for n in v["makers"]})
    isins = load_json(os.path.join(ROOT, "isins.json"))["isin"]

    state = {name[:-5]: load_json(os.path.join(a.state, name))
             for name in (os.listdir(a.state) if os.path.isdir(a.state) else []) if name.endswith(".json")}
    run = Run()
    writes = []

    def emit(doc_id, doc):
        p = os.path.join(a.out, f"{doc_id}.json")
        with open(p, "w") as f:
            json.dump(doc, f, separators=(",", ":"))
        writes.append({"op": "set", "collection": "vahan", "doc_id": doc_id, "file_path": os.path.abspath(p)})

    try:
        regs = fetch_registrations(years, makers, profile)
        trade_date, closes, bhav_sha = fetch_prices(isins, today)
    except SourceError as e:
        run.check(False, "source answered", str(e))
        regs, trade_date, closes, bhav_sha = None, None, {}, None

    revisions = []
    if regs:
        for y in years:
            prev = (state.get(f"series-{y}") or {}).get("reg")
            revisions += check_year(run, y, regs[y], prev, cur_month, baseline)

        # has the source posted anything since yesterday?
        cur = regs[today.year]["market"]["total"].get(cur_month)
        prev_series = (state.get(f"series-{today.year}") or {}).get("reg")
        prev_cur = prev_series["market"]["total"].get(cur_month) if prev_series else None
        if prev_cur is not None and cur == prev_cur and today.weekday() != 6:
            print("source not updated since the last run")
            json.dump({"status": "not_updated", "run": run_id}, open(os.path.join(a.out, "report.json"), "w"))
            return 3

        # prices
        run.check(set(closes) == set(isins), "every ticker has a close",
                  f"missing: {', '.join(sorted(set(isins) - set(closes)))}")
        prev_prices = (state.get(f"prices-{trade_date[:4]}") or {}) if trade_date else {}
        last = {}
        for d in sorted(prev_prices.get("closes", {})):
            last.update(prev_prices["closes"][d])
        held = list((state.get("held") or {}).get("items", []))
        seen = {(h["ticker"], h["date"]) for h in held}
        for tk, c in closes.items():
            if tk in last and last[tk] and abs(c / last[tk] - 1) > PRICE_JUMP and (tk, trade_date) not in seen:
                held.append({"ticker": tk, "date": trade_date, "from": last[tk], "to": c, "confirmed": False})
                run.check(False, "no unexplained price jump",
                          f"{tk} moved {c / last[tk] - 1:+.1%} on {trade_date} ({last[tk]} -> {c}); held until confirmed",
                          blocking=False)

    status = {
        "run": run_id, "ranAt": t.isoformat(timespec="seconds"),
        "ok": not run.blockers, "blockers": run.blockers, "warnings": run.warnings,
        "checksPassed": len(run.passed), "checksTotal": len(run.passed) + len(run.blockers) + len(run.warnings),
        "lastGood": None if run.blockers else t.isoformat(timespec="seconds"),
        "dataAsOf": t.isoformat(timespec="seconds") if not run.blockers else
                    (state.get("status") or {}).get("dataAsOf"),
        "pricesTo": trade_date if not run.blockers else (state.get("status") or {}).get("pricesTo"),
        "source": "analytics.parivahan.gov.in public dashboard; NSE CM bhavcopy",
    }
    if run.blockers:
        status["lastGood"] = (state.get("status") or {}).get("lastGood")
        emit("status", status)
    else:
        for y in years:
            emit(f"series-{y}", {"year": y, "readAt": status["dataAsOf"], "reg": regs[y]})
        # the day's month-to-date reading, appended to this month's curve
        dkey = f"daily-{cur_month}"
        daily = state.get(dkey) or {"month": cur_month, "readings": []}
        reading = {"readAt": status["dataAsOf"], "date": today.isoformat(),
                   "market": regs[today.year]["market"]["total"].get(cur_month),
                   "marketSegments": {k: v.get(cur_month) for k, v in regs[today.year]["market"]["segments"].items()},
                   "makers": {n: {"total": m["total"].get(cur_month),
                                  "segments": {k: v.get(cur_month) for k, v in m["segments"].items()}}
                              for n, m in regs[today.year]["makers"].items()}}
        daily["readings"] = [r for r in daily["readings"] if r["date"] != today.isoformat()] + [reading]
        emit(dkey, daily)
        pkey = f"prices-{trade_date[:4]}"
        prices = state.get(pkey) or {"year": trade_date[:4], "closes": {}}
        prices["closes"][trade_date] = closes
        prices["bhavSha256"] = {**prices.get("bhavSha256", {}), trade_date: bhav_sha}
        emit(pkey, prices)
        emit("held", {"items": held})
        # what Vahan added since the last run, into this week's figures
        prev_regs = {y: (state.get(f"series-{y}") or {}).get("reg") for y in years}
        inc = weekly.increments(regs, {y: r for y, r in prev_regs.items() if r}, cur_month)
        wid = weekly.doc_id(today)
        emit(wid, weekly.accumulate(state.get(wid), today, inc))
        if revisions:
            rkey = f"revisions-{today.year}"
            rev = state.get(rkey) or {"items": []}
            rev["items"] += [{**r, "seen": today.isoformat()} for r in revisions]
            emit(rkey, rev)
            run.check(False, "closed months unrevised", f"{len(revisions)} maker-month figures revised", blocking=False)
            status["warnings"] = run.warnings
        emit("map", mapping)
        emit("status", status)

    rk = f"runs-{cur_month}"
    runs = state.get(rk) or {"items": []}
    runs["items"] = runs["items"][-60:] + [{k: status[k] for k in ("run", "ranAt", "ok", "checksPassed", "checksTotal")}
                                          | {"blockers": run.blockers, "warnings": len(run.warnings)}]
    emit(rk, runs)
    with open(os.path.join(a.out, "writes.json"), "w") as f:
        json.dump(writes, f, indent=1)
    with open(os.path.join(a.out, "report.json"), "w") as f:
        json.dump(status, f, indent=1)
    print(json.dumps({k: status[k] for k in ("ok", "checksPassed", "checksTotal")} | {"writes": len(writes)}))
    return 0 if not run.blockers else 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
