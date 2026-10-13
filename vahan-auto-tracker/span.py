"""Per-contract SPAN data for the open positions, from NSE's own end-of-day files.

The Kite MCP gives the margin blocked only as account totals (utilised span, exposure, option
premium). To show capital blocked per ticker, the dashboard estimates it the way the exchange
computes it, from three NSE files of the same trading day:

  SPAN risk parameters  nsearchives.nseindia.com/archives/nsccl/span/nsccl.YYYYMMDD.s.zip
                        16 scenario losses per contract, per unit (positive = loss to a long)
  F&O bhavcopy          nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_..._YYYYMMDD_...
                        trading symbol -> expiry, strike, option type, lot size
  exposure margin       nsearchives.nseindia.com/archives/exp_lim/ael_DDMMYYYY.csv
                        ELM % per stock; index derivatives are 2% by SEBI's rule (not in the file)

Only the contracts in the latest positions snapshot (the dashboard's positions/latest) are kept,
so the document stays small. A contract not found is listed, never guessed.

Usage: python3 span.py --positions /tmp/state/positions/latest.json --out /tmp/span [--today YYYY-MM-DD]
Exit: 0 written (writes.json lists the documents), 2 blocked (status only), 1 failure.
"""
import argparse
import csv
import hashlib
import io
import json
import os
import sys
import traceback
import xml.etree.ElementTree as ET
import zipfile
from datetime import date, timedelta

import requests

from ingest import Run, load_json, now_ist

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128 Safari/537.36"
SPAN_URL = "https://nsearchives.nseindia.com/archives/nsccl/span/nsccl.{d}.s.zip"
FO_URL = "https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{d}_F_0000.csv.zip"
AEL_URL = "https://nsearchives.nseindia.com/archives/exp_lim/ael_{dmy}.csv"
INDEX_ELM = 2.0            # % of notional, index futures and short index options (SEBI)
SCENARIOS = 16


class SourceError(Exception):
    pass


def get(url):
    for i in range(3):
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=120)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.content
        except requests.RequestException:
            if i == 2:
                raise
    return None


def unzip_one(blob):
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        return z.read(z.namelist()[0])


def fetch_files(today):
    """The latest trading day before today for which all three files exist."""
    d = today - timedelta(days=1)
    for _ in range(10):
        if d.weekday() < 5:
            fo = get(FO_URL.format(d=d.strftime("%Y%m%d")))
            if fo and fo[:2] == b"PK":
                span = get(SPAN_URL.format(d=d.strftime("%Y%m%d")))
                ael = get(AEL_URL.format(dmy=d.strftime("%d%m%Y")))
                if not span or span[:2] != b"PK" or not ael:
                    raise SourceError(f"F&O bhavcopy for {d} is out but the SPAN or exposure-margin file is not")
                return d, {"fo": fo, "span": span, "ael": ael}
        d -= timedelta(days=1)
    raise SourceError("no F&O bhavcopy in the last 10 days")


# ---------------------------------------------------------------- parse

def parse_fo(blob):
    rows = csv.DictReader(io.TextIOWrapper(io.BytesIO(unzip_one(blob)), encoding="utf-8"))
    out, dates = {}, set()
    for r in rows:
        dates.add(r["TradDt"])
        out[r["FinInstrmNm"]] = {
            "u": r["TckrSymb"], "tp": r["FinInstrmTp"], "pe": r["XpryDt"].replace("-", ""),
            "k": float(r["StrkPric"]) if r["StrkPric"] else None, "o": (r["OptnTp"] or "")[:1] or None,
            "lot": int(float(r["NewBrdLotQty"] or 0)), "close": float(r["ClsPric"] or 0),
            "und": float(r["UndrlygPric"] or 0)}
    return out, dates


def parse_ael(blob):
    out = {}
    for r in csv.reader(io.StringIO(blob.decode("utf-8", "replace"))):
        if len(r) >= 6 and r[0].strip().isdigit():
            out.setdefault(r[1].strip(), {})[r[2].strip()] = float(r[5])
    return out


def ra_of(el):
    ra = el.find("ra")
    if ra is None:
        return None, None
    a = [float(x.text) for x in ra.findall("a")]
    d = ra.findtext("d")
    return a, (float(d) if d is not None else None)


def parse_span(blob, unders):
    """{u: {"fut": {pe: {...}}, "opt": {(pe, o, k): {...}}, "spot": p, "scan": priceScan,
    "spread": rate, "som": rate}} for the given underlyings, and the file's business date."""
    out = {u: {"fut": {}, "opt": {}} for u in unders}
    biz = None
    for ev, el in ET.iterparse(io.BytesIO(unzip_one(blob)), events=("end",)):
        tag = el.tag
        if tag == "date" and biz is None:
            biz = (el.text or "").strip()
        elif tag in ("phyPf", "futPf", "oopPf"):
            u = el.findtext("pfCode")
            if u in out:
                if tag == "phyPf":
                    phy = el.find("phy")
                    out[u]["spot"] = float(phy.findtext("p"))
                elif tag == "futPf":
                    for f in el.findall("fut"):
                        a, d = ra_of(f)
                        out[u]["fut"][f.findtext("pe")] = {"ra": a, "d": d, "p": float(f.findtext("p"))}
                        sr = f.find("scanRate")
                        if sr is not None:
                            out[u]["scan"] = float(sr.findtext("priceScan"))
                else:
                    for s in el.findall("series"):
                        pe = s.findtext("pe")
                        for o in s.findall("opt"):
                            a, d = ra_of(o)
                            out[u]["opt"][(pe, o.findtext("o"), float(o.findtext("k")))] = {"ra": a, "d": d, "p": float(o.findtext("p"))}
            el.clear()
        elif tag == "ccDef":
            u = el.findtext("cc")
            if u in out:
                rates = [float(r.findtext("val")) for ds in el.findall("dSpread") for r in ds.findall("rate")]
                out[u]["spread"] = max(rates) if rates else 0.0
                som = [float(r.findtext("val")) for t in el.findall("somTiers/tier") for r in t.findall("rate")]
                out[u]["som"] = max(som) if som else 0.0
            el.clear()
    return out, biz


# ---------------------------------------------------------------- the estimate (the page computes the same)

def estimate(lines, cc):
    """SPAN estimate for one underlying.
    lines: [{q, ra[16], d, p, k (FUT|CE|PE), up}] with q in units, signed.
    Requirement = max(scanning risk + calendar spread charge - net option value, short option minimum).
    Exposure = ELM% x notional of futures and short options. Long option premium is paid, not margined."""
    scan = max(0.0, max(sum(l["q"] * l["ra"][s] for l in lines) for s in range(SCENARIOS)))
    by_pe = {}
    for l in lines:
        by_pe[l["pe"]] = by_pe.get(l["pe"], 0.0) + l["q"] * (l["d"] or 0)
    longs = sum(v for v in by_pe.values() if v > 0)
    shorts = -sum(v for v in by_pe.values() if v < 0)
    spread = min(longs, shorts) * cc.get("spread", 0) if len(by_pe) > 1 else 0.0
    nov = sum(l["q"] * l["p"] for l in lines if l["k"] in ("CE", "PE"))
    short_opt = sum(-l["q"] for l in lines if l["k"] in ("CE", "PE") and l["q"] < 0)
    span = max(scan + spread - nov, short_opt * cc.get("som", 0), 0.0)
    elm = cc["elm"] / 100.0
    exposure = sum(abs(l["q"]) * (l["p"] if l["k"] == "FUT" else cc["spot"]) * elm
                   for l in lines if l["k"] == "FUT" or l["q"] < 0)
    return {"scan": round(scan, 2), "spread": round(spread, 2), "nov": round(nov, 2),
            "span": round(span, 2), "exposure": round(exposure, 2)}


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--positions", required=True, help="positions/latest.json from the dashboard database")
    ap.add_argument("--out", required=True)
    ap.add_argument("--today", help="YYYY-MM-DD, for tests")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    t = now_ist()
    today = date.fromisoformat(a.today) if a.today else t.date()
    run, writes = Run(), []

    def emit(collection, doc_id, doc):
        p = os.path.join(a.out, f"{collection}-{doc_id}.json")
        with open(p, "w") as f:
            json.dump(doc, f, separators=(",", ":"))
        writes.append({"op": "set", "collection": collection, "doc_id": doc_id, "file_path": os.path.abspath(p)})

    snap = load_json(a.positions) or {}
    fo_rows = [r for r in snap.get("rows", []) if r.get("k") in ("FUT", "CE", "PE")]
    doc = None
    status = {"ranAt": t.isoformat(timespec="seconds"), "positionsTakenAt": snap.get("takenAt"), "lines": len(fo_rows)}

    if not fo_rows:
        run.check(True, "positions read", "")
        status |= {"ok": True, "note": "no futures or options in the positions snapshot"}
    else:
        try:
            d, files = fetch_files(today)
        except SourceError as e:
            run.check(False, "NSE files answered", str(e))
            d, files = None, None
        if files:
            fo, fo_dates = parse_fo(files["fo"])
            ael = parse_ael(files["ael"])
            run.check(fo_dates == {d.isoformat()}, "bhavcopy date", f"bhavcopy dates {sorted(fo_dates)} for {d}")
            found, missing = {}, []
            for r in fo_rows:
                m = fo.get(r["s"])
                if r.get("ex") not in (None, "NFO") or not m:
                    missing.append({"s": r["s"], "why": "not an NSE F&O contract in the bhavcopy" if not m else "not on NSE"})
                    continue
                found[r["s"]] = m
            unders = sorted({m["u"] for m in found.values()})
            span, biz = parse_span(files["span"], unders)
            run.check(biz == d.strftime("%Y%m%d"), "SPAN file date", f"SPAN business date {biz}, expected {d:%Y%m%d}")
            contracts, cc = {}, {}
            for u in unders:
                s = span[u]
                el = ael.get(u, {})
                index = any(m["tp"] in ("IDF", "IDO") for m in found.values() if m["u"] == u)
                pct = INDEX_ELM if index else el.get("OTH")
                ok = pct is not None and 0 < pct <= 20 and "spot" in s
                run.check(ok, f"{u} exposure rate and price", f"{u}: ELM {pct}, spot {'spot' in s}")
                if ok:
                    cc[u] = {"spot": s["spot"], "scan": s.get("scan"), "spread": s.get("spread", 0.0),
                             "som": s.get("som", 0.0), "elm": pct, "elmSource": "SEBI index rule" if index else "NSE ael file"}
            for sym, m in found.items():
                s = span[m["u"]]
                c = s["fut"].get(m["pe"]) if m["o"] is None else s["opt"].get((m["pe"], m["o"], m["k"]))
                if not c or not c["ra"]:
                    missing.append({"s": sym, "why": "not in the SPAN file"})
                    continue
                good = len(c["ra"]) == SCENARIOS and all(isinstance(x, float) for x in c["ra"])
                if run.check(good, f"{sym} risk array", f"{sym}: {len(c['ra'])} scenarios"):
                    contracts[sym] = {"u": m["u"], "pe": m["pe"], "ra": c["ra"], "d": c["d"], "p": c["p"], "lot": m["lot"]}
            run.check(not missing, "every held contract found", missing, blocking=False)
            doc = {"tradeDate": d.isoformat(), "builtAt": status["ranAt"], "positionsTakenAt": snap.get("takenAt"),
                   "sha256": {k: hashlib.sha256(v).hexdigest() for k, v in files.items()},
                   "contracts": contracts, "cc": cc, "missing": missing,
                   "method": "SPAN = max(scanning risk + calendar spread - net option value, short option minimum); "
                             "exposure = ELM% x notional of futures and short options"}
        status |= {"ok": not run.blockers, "tradeDate": d.isoformat() if d else None,
                   "contracts": len(doc["contracts"]) if doc else 0, "missing": len(doc["missing"]) if doc else 0}

    status |= {"checksPassed": len(run.passed), "checksTotal": len(run.passed) + len(run.blockers) + len(run.warnings),
               "blockers": run.blockers, "warnings": run.warnings}
    if doc and not run.blockers:
        emit("margin", "span-latest", doc)
    emit("margin", "status", status)
    with open(os.path.join(a.out, "writes.json"), "w") as f:
        json.dump(writes, f, indent=1)
    print(json.dumps({k: status.get(k) for k in ("ok", "tradeDate", "contracts", "missing", "checksPassed", "checksTotal")}
                     | {"writes": len(writes)}))
    return 0 if not run.blockers else 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
