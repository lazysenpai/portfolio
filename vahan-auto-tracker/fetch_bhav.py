"""Fetch NSE's capital-market bhavcopy for one trading day and print closes for given tickers.

Usage: python3 fetch_bhav.py YYYYMMDD [TICKER ...]
"""
import csv, hashlib, io, sys, zipfile
import requests

URL = "https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{d}_F_0000.csv.zip"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128 Safari/537.36"


def fetch(day):
    r = requests.get(URL.format(d=day), headers={"User-Agent": UA}, timeout=60)
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        name = z.namelist()[0]
        rows = list(csv.DictReader(io.TextIOWrapper(z.open(name), encoding="utf-8")))
    return hashlib.sha256(r.content).hexdigest(), rows


if __name__ == "__main__":
    day, tickers = sys.argv[1], set(sys.argv[2:])
    sha, rows = fetch(day)
    eq = [r for r in rows if r["SctySrs"] == "EQ" and (not tickers or r["TckrSymb"] in tickers)]
    print({"sha256": sha, "rows": len(rows), "eq_matched": len(eq)})
    for r in eq:
        print(r["TckrSymb"], r["TradDt"], "close", r["ClsPric"], "prev", r["PrvsClsgPric"], "vol", r["TtlTradgVol"])
