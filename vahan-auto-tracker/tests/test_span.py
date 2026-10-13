"""span.py: the estimate is worked by hand, hedges lower it, and bad or missing files never write data.

Run: python3 -m pytest -q tests
"""
import io
import json
import os
import sys
import zipfile
from datetime import date

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import span                                                          # noqa: E402

CC = {"spot": 1000.0, "spread": 10.0, "som": 0.0, "elm": 3.5}
# One unit of a future: loses 100 if the price falls a full scan range, gains 100 if it rises.
FUT = [0, 0, -33, -33, 33, 33, -67, -67, 67, 67, -100, -100, 100, 100, -70, 70]
# A call that gains on a rise and loses at most its premium (8) on a fall.
CALL = [0, 0, -15, -15, 6, 6, -35, -35, 7, 7, -60, -60, 8, 8, -45, 8]


def line(ra, q, k="FUT", pe="20261027", d=1.0, p=1000.0):
    return {"ra": [float(x) for x in ra], "q": q, "k": k, "pe": pe, "d": d, "p": p}


def test_hand_worked_long_future():
    # 50 long: worst scenario is a full fall, 50 x 100 = 5,000. Exposure 3.5% of 50 x 1,000 = 1,750.
    e = span.estimate([line(FUT, 50)], CC)
    assert e["scan"] == 5000 and e["span"] == 5000 and e["exposure"] == 1750


def test_short_future_takes_the_rise():
    e = span.estimate([line(FUT, -50)], CC)
    assert e["span"] == 5000 and e["exposure"] == 1750


def test_long_call_is_premium_not_margin():
    # Net option value (50 x 8 = 400) cancels the scanning risk; the premium is paid, not blocked as SPAN.
    e = span.estimate([line(CALL, 50, k="CE", d=0.5, p=8.0)], CC)
    assert e["span"] == 0 and e["exposure"] == 0


def test_hedge_is_margined_below_its_legs():
    fut, short_call = line(FUT, 50), line(CALL, -50, k="CE", d=0.5, p=8.0)
    alone = span.estimate([fut], CC)["span"] + span.estimate([short_call], CC)["span"]
    both = span.estimate([fut, short_call], CC)["span"]
    assert both < alone


def test_calendar_spread_charge():
    # Long Oct, short Nov: the price risk nets to zero, so the spread charge is all that is left.
    e = span.estimate([line(FUT, 50, pe="20261027"), line(FUT, -50, pe="20261123")], CC)
    assert e["scan"] == 0 and e["spread"] == 50 * 10 and e["span"] == 500


# ---------------------------------------------------------------- the run

SPAN_XML = """<?xml version="1.0"?><spanFile><pointInTime><date>{biz}</date><clearingOrg><exchange>
<phyPf><pfCode>ABC</pfCode><phy><p>1000.00</p></phy></phyPf>
<futPf><pfCode>ABC</pfCode><fut><pe>20261027</pe><p>1001.00</p><scanRate><priceScan>100</priceScan></scanRate>
<ra><r>1</r>{ra}<d>1.0</d></ra></fut></futPf>
</exchange><ccDef><cc>ABC</cc><somTiers><tier><rate><r>1</r><val>0</val></rate></tier></somTiers></ccDef>
</clearingOrg></pointInTime></spanFile>"""
FO_CSV = ("TradDt,FinInstrmTp,TckrSymb,XpryDt,StrkPric,OptnTp,FinInstrmNm,ClsPric,UndrlygPric,NewBrdLotQty\n"
          "{d},STF,ABC,2026-10-27,,,ABC26OCTFUT,1001,1000,50\n")
AEL_CSV = "Sr No.,Symbol,Instrument Type,Normal ELM Margin%,Additional,Total applicable ELM%\n1,ABC,OTH,3.5,0,3.5\n"


def zipped(text):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("f", text)
    return b.getvalue()


def files(biz="20261009", fo_date="2026-10-09"):
    ra = "".join(f"<a>{x}</a>" for x in FUT)
    return {"span": zipped(SPAN_XML.format(biz=biz, ra=ra)), "fo": zipped(FO_CSV.format(d=fo_date)),
            "ael": AEL_CSV.encode()}


def run_main(tmp_path, monkeypatch, rows, fx):
    pos = tmp_path / "latest.json"
    pos.write_text(json.dumps({"takenAt": 1, "rows": rows}))
    monkeypatch.setattr(span, "fetch_files", lambda today: (date(2026, 10, 9), fx))
    monkeypatch.setattr(sys, "argv", ["span.py", "--positions", str(pos), "--out", str(tmp_path / "out"), "--today", "2026-10-10"])
    code = span.main()
    writes = json.loads((tmp_path / "out" / "writes.json").read_text())
    return code, {w["doc_id"]: json.loads(open(w["file_path"]).read()) for w in writes}


ROW = {"s": "ABC26OCTFUT", "ex": "NFO", "k": "FUT", "q": 50}


def test_good_files_write_the_contract(tmp_path, monkeypatch):
    code, docs = run_main(tmp_path, monkeypatch, [ROW], files())
    assert code == 0 and docs["span-latest"]["contracts"]["ABC26OCTFUT"]["ra"][12] == 100
    assert docs["span-latest"]["cc"]["ABC"]["elm"] == 3.5


def test_missing_contract_is_listed_never_guessed(tmp_path, monkeypatch):
    code, docs = run_main(tmp_path, monkeypatch, [ROW, dict(ROW, s="XYZ26OCTFUT")], files())
    assert code == 0 and "XYZ26OCTFUT" not in docs["span-latest"]["contracts"]
    assert [m["s"] for m in docs["span-latest"]["missing"]] == ["XYZ26OCTFUT"]


def test_wrong_span_date_blocks(tmp_path, monkeypatch):
    code, docs = run_main(tmp_path, monkeypatch, [ROW], files(biz="20261008"))
    assert code == 2 and set(docs) == {"status"} and not docs["status"]["ok"]


def test_wrong_bhavcopy_date_blocks(tmp_path, monkeypatch):
    code, docs = run_main(tmp_path, monkeypatch, [ROW], files(fo_date="2026-10-08"))
    assert code == 2 and set(docs) == {"status"}


def test_no_derivatives_writes_status_only(tmp_path, monkeypatch):
    code, docs = run_main(tmp_path, monkeypatch, [{"s": "ITC", "ex": "NSE", "k": "EQ", "q": 1}], files())
    assert code == 0 and set(docs) == {"status"}
