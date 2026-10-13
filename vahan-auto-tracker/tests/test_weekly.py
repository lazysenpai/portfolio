"""weekly.py: a week is exactly what Vahan added between runs, late entries kept apart.

Run: python3 -m pytest -q tests
"""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import weekly                                                        # noqa: E402


def blk(sep, oct_, pv_oct=None):
    pv = pv_oct if pv_oct is not None else oct_ - 10
    return {"total": {"2026-09": sep, "2026-10": oct_}, "segments": {"PV": {"2026-09": sep - 5, "2026-10": pv}}}


def regs(sep, oct_, maker=True):
    r = {"market": blk(sep * 3, oct_ * 3), "makers": {}}
    if maker:
        r["makers"]["MAKER A"] = blk(sep, oct_)
    return {2026: r}


def test_increment_is_the_difference_and_late_is_separate():
    inc = weekly.increments(regs(1000, 120), regs(990, 100), "2026-10")
    a = inc["makers"]["MAKER A"]
    assert a["total"] == 30 and a["late"] == 10 and a["segments"]["PV"] == 30
    assert inc["market"]["total"] == 90 and inc["market"]["late"] == 30


def test_a_maker_not_stored_before_is_skipped_not_counted_whole():
    prev = regs(990, 100, maker=False)
    inc = weekly.increments(regs(1000, 120), prev, "2026-10")
    assert "MAKER A" not in inc["makers"] and inc["skipped"]


def test_a_year_not_stored_before_is_skipped():
    inc = weekly.increments(regs(1000, 120), {}, "2026-10")
    assert inc["market"] is None and inc["skipped"] == ["2026: no stored year"]


def test_runs_accumulate_into_monday_to_sunday_weeks():
    doc = None
    days = [(date(2026, 10, 12), 20), (date(2026, 10, 13), 25), (date(2026, 10, 18), 5), (date(2026, 10, 19), 40)]
    base = 100
    for d, add in days:
        inc = weekly.increments(regs(1000, base + add), regs(1000, base), "2026-10")
        doc = weekly.accumulate(doc if weekly.doc_id(d) == "weekly-2026-10" else doc, d, inc)
        base += add
    w = doc["weeks"]
    assert set(w) == {"2026-10-12", "2026-10-19"}
    assert w["2026-10-12"]["makers"]["MAKER A"]["total"] == 50 and w["2026-10-19"]["makers"]["MAKER A"]["total"] == 40
    assert w["2026-10-12"]["to"] == "2026-10-18" and w["2026-10-12"]["reads"] == {"2026-10-12": 60, "2026-10-13": 75, "2026-10-18": 15}


def test_two_runs_on_one_day_add_up():
    doc = weekly.accumulate(None, date(2026, 10, 13), weekly.increments(regs(1000, 110), regs(1000, 100), "2026-10"))
    doc = weekly.accumulate(doc, date(2026, 10, 13), weekly.increments(regs(1000, 115), regs(1000, 110), "2026-10"))
    assert doc["weeks"]["2026-10-12"]["makers"]["MAKER A"]["total"] == 15


def test_unknown_late_stays_unknown_for_the_week():
    doc = weekly.accumulate(None, date(2026, 10, 12), {"market": {"total": 5, "late": None, "segments": {}},
                                                       "makers": {"MAKER A": {"total": 5, "late": None, "segments": {}}}}, "seed")
    doc = weekly.accumulate(doc, date(2026, 10, 13), weekly.increments(regs(1000, 110), regs(990, 100), "2026-10"))
    a = doc["weeks"]["2026-10-12"]["makers"]["MAKER A"]
    assert a["total"] == 25 and a["late"] is None


def test_week_doc_is_keyed_by_the_mondays_month():
    assert weekly.doc_id(date(2026, 11, 1)) == "weekly-2026-10"          # Sunday 1 Nov belongs to the week of 26 Oct
    assert weekly.doc_id(date(2026, 11, 2)) == "weekly-2026-11"
