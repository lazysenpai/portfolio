"""Every blocking check fails its broken case and passes the clean one.

Run: python3 -m pytest -q tests
"""
import copy
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fetch_analytics import to_months, SourceError                 # noqa: E402
from ingest import Run, check_year                                  # noqa: E402
from segments import build, key, requests_for, segments_of, own_groups, CV, BLOCK, ALL6, SINGLE   # noqa: E402

CUR = "2026-10"
MONTHS = [f"2026-{m:02d}" for m in range(1, 11)]


def maker(pv=900, cv=100, w2=500, overlap_free=True, total_extra=10, cur=None):
    """A maker in 2W, PV and CV, built through segments.build from what the source would return."""
    f = lambda v: {m: (cur if (cur is not None and m == CUR) else v) for m in MONTHS}
    segs = ["2W", "PV", "CV"]
    own = pv + cv + w2 if overlap_free else pv + cv + w2 - 50
    got = {None: f(pv + cv + w2 + total_extra), key(CV): f(cv), key(BLOCK): f(pv + cv),
           key(SINGLE["2W"]): f(w2), key(own_groups(segs)): f(own)}
    return build(got, segs)


def year(**kw):
    m = maker(**kw)
    return {"market": copy.deepcopy(m), "makers": {"MAKER A": m}}


def run(cur, prev=None, baseline=None):
    r = Run()
    revisions = check_year(r, 2026, cur, prev, CUR, baseline)
    return r, revisions


def names(items):
    return sorted({i["check"] for i in items})


# ---------------------------------------------------------------- shape

def test_to_months_clean():
    rows = [{"yearAsString": "2026-October", "registeredVehicleCount": 5},
            {"yearAsString": "2026-January", "registeredVehicleCount": 7}]
    assert to_months(rows, 2026) == {"2026-01": 7, "2026-10": 5}


@pytest.mark.parametrize("rows", [
    {"error": "x"},                                                          # not a list
    [{"yearAsString": "2026-Octember", "registeredVehicleCount": 5}],          # bad month
    [{"yearAsString": "2025-October", "registeredVehicleCount": 5}],           # wrong year
    [{"yearAsString": "2026-October", "registeredVehicleCount": -1}],          # negative
    [{"yearAsString": "2026-October", "registeredVehicleCount": "5"}],         # not a number
    [{"yearAsString": "2026-May", "registeredVehicleCount": 1},
     {"yearAsString": "2026-May", "registeredVehicleCount": 2}],               # month twice
])
def test_to_months_rejects(rows):
    with pytest.raises(SourceError):
        to_months(rows, 2026)


# ---------------------------------------------------------------- segments

def test_segments_from_groups():
    assert segments_of(["Four Wheeler", "Goods Vehicle"]) == ["PV", "CV"]
    assert segments_of(["Bus"]) == ["CV"]
    assert segments_of(["Two Wheeler"]) == ["2W"]


def test_union_check_only_across_independent_blocks():
    reqs = requests_for(["PV", "CV"])
    assert CV in reqs and BLOCK in reqs and len(reqs) == 3          # PV+CV add back exactly: no union needed
    assert ["Two Wheeler", "Three Wheeler"] in requests_for(["2W", "3W"])
    assert ALL6 not in requests_for(["2W", "3W"])


def test_pv_is_block_minus_cv():
    b = maker(pv=900, cv=100)
    assert b["segments"]["PV"]["2026-03"] == 900 and b["segments"]["CV"]["2026-03"] == 100


# ---------------------------------------------------------------- reconciliation

def test_clean_year_passes():
    r, _ = run(year())
    assert r.blockers == [] and r.warnings == []


def test_double_counting_blocks():
    r, _ = run(year(overlap_free=False))                             # segments exceed their union by 50
    assert names(r.blockers) == ["no vehicle counted twice"]


def test_segments_above_total_block():
    r, _ = run(year(total_extra=-60))                                # segments 1,500, total 1,440
    assert "segments within total" in names(r.blockers)


def test_negative_pv_blocks():
    y = year()
    y["makers"]["MAKER A"]["segments"]["PV"]["2026-04"] = -3
    r, _ = run(y)
    assert names(r.blockers) == ["segments never negative"]


def test_live_month_slack_allowed():
    y = year()
    y["makers"]["MAKER A"]["own"][CUR] -= 3                          # moved between requests
    r, _ = run(y)
    assert r.blockers == []


def test_unassigned_share_warns_above_baseline_only():
    y = year(total_extra=600)                                        # 600 of 2,100 outside segments: 28.6%
    r, _ = run(y, baseline={"MAKER A": 0.27})
    assert r.blockers == [] and r.warnings == []
    r, _ = run(y, baseline={"MAKER A": 0.10})
    assert r.blockers == [] and names(r.warnings) == ["maker outside its usual segments"]


# ---------------------------------------------------------------- day over day

def test_closed_month_shrinking_blocks():
    prev, cur = year(), year()
    cur["market"]["total"]["2026-04"] = 1300                         # -14% overnight
    r, _ = run(cur, prev)
    assert "closed months never shrink" in names(r.blockers)


def test_closed_month_growth_is_a_logged_revision():
    # late registrations (Telangana uploads in batches) only add: warn and log, never block
    prev, cur = year(), year()
    cur["market"]["total"]["2026-04"] = 1600                         # +6.7% overnight
    cur["makers"]["MAKER A"]["total"]["2026-04"] = 1600
    r, revisions = run(cur, prev)
    assert "closed months stable" in names(r.warnings) and "closed months stable" not in names(r.blockers)
    assert {"maker": "MAKER A", "month": "2026-04", "from": 1510, "to": 1600} in revisions


def test_mtd_shrinking_blocks():
    prev, cur = year(cur=1510), year(cur=1510)
    cur["makers"]["MAKER A"]["total"][CUR] = 1400                     # was 1,510
    r, _ = run(cur, prev)
    assert "month to date never shrinks" in names(r.blockers)


def test_closed_month_revision_is_logged_not_blocked():
    prev, cur = year(), year()
    cur["makers"]["MAKER A"]["total"]["2026-02"] = 1511               # was 1,510
    r, revisions = run(cur, prev)
    assert r.blockers == []
    assert revisions == [{"maker": "MAKER A", "month": "2026-02", "from": 1510, "to": 1511}]


def test_prev_is_not_mutated():
    prev = year()
    snapshot = copy.deepcopy(prev)
    run(year(), prev)
    assert prev == snapshot


def test_three_wheeled_ambulance_is_counted_once():
    # a maker in 3W and CV: 13 of its 3W are also in the Ambulance group
    segs = ["3W", "CV"]
    f = lambda v: {m: v for m in MONTHS}
    w3, goods_bus_amb, both = 1000, 500, 13
    got = {None: f(w3 + goods_bus_amb - both), key(SINGLE["3W"]): f(w3),
           key(CV + SINGLE["3W"]): f(w3 + goods_bus_amb - both), key(own_groups(segs)): f(w3 + goods_bus_amb - both)}
    b = build(got, segs)
    assert b["segments"]["CV"]["2026-04"] == goods_bus_amb - both
    r = Run()
    check_year(r, 2026, {"market": b, "makers": {"MAKER B": b}}, None, CUR)
    assert r.blockers == []
