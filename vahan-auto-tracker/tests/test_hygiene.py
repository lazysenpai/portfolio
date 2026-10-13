"""hygiene.py: the shipped configuration is clean, and each kind of breakage is caught.

Run: python3 -m pytest -q tests
"""
import copy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import hygiene                                                       # noqa: E402
from ingest import Run                                               # noqa: E402

ROOT = hygiene.ROOT
MAP = json.load(open(os.path.join(ROOT, "maker_map.json")))
PROFILE = json.load(open(os.path.join(ROOT, "maker_groups.json")))["groups"]
ISINS = json.load(open(os.path.join(ROOT, "isins.json")))["isin"]


def blockers(mapping=MAP, profile=PROFILE, isins=ISINS):
    r = Run()
    hygiene.check_config(r, mapping, profile, isins)
    return [b["detail"] for b in r.blockers]


def test_shipped_configuration_is_clean():
    assert blockers() == []


def test_maker_in_two_tickers_blocks():
    m = copy.deepcopy(MAP)
    m["tickers"]["TMCV"]["makers"].append(m["tickers"]["MARUTI"]["makers"][0])
    assert any("maps to both" in b for b in blockers(mapping=m))


def test_unprofiled_maker_blocks():
    p = dict(PROFILE)
    p.pop(MAP["tickers"]["MARUTI"]["makers"][0])
    assert any("would read zero" in b for b in blockers(profile=p))


def test_ticker_without_isin_blocks():
    i = dict(ISINS)
    i.pop("MARUTI")
    assert any("no ISIN" in b for b in blockers(isins=i))


def test_unclassified_group_blocks(monkeypatch):
    monkeypatch.setattr(hygiene, "GROUPS", hygiene.GROUPS + ["Hovercraft"])
    assert any("Hovercraft" in b for b in blockers())


def fada(v, months=("2026-07", "2026-08", "2026-09")):
    return {"months": list(months), "cats": [{"k": "PV", "makers": [{"m": "Maruti", "sym": "MARUTI", "v": v}]}]}


def series(v):
    name = MAP["tickers"]["MARUTI"]["makers"][0]
    return {"2026": {"makers": {name: {"segments": {"PV": dict(zip(["2026-07", "2026-08", "2026-09"], v))}}}}}


def verdicts(f, s):
    r = Run()
    return [x["verdict"] for x in hygiene.reconcile(r, f, s, MAP)], r


def test_reconcile_verdicts():
    v, r = verdicts(fada([100, 100, 100]), series([102, 106, 85]))
    assert v == ["agrees", "late registrations", "unexplained"]
    assert len(r.blockers) == 1 and len(r.warnings) == 1


def test_latest_month_above_fada_is_not_excused_as_late():
    v, _ = verdicts(fada([100, 100, 100]), series([100, 100, 106]))
    assert v[-1] == "unexplained"
