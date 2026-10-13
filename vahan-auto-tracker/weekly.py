"""Weekly registrations, built from what each daily run finds Vahan has added.

Vahan publishes only yearly, quarterly and monthly counts (its dashboard offers nothing finer),
so a week is the sum of the day-on-day increments the ingest observes: for every maker and
segment, today's counts minus the counts stored by the previous run, over every month of every
year read. Vahan posts once a day (around 08:00-10:00 IST), so a run on date D mostly adds
registrations made on D-1; weeks run Monday to Sunday by the date the run read them.

Late registrations for earlier months (Telangana uploads in batches) are real but backdated;
they are counted in the week they appear and kept separately as "late", so a batch never
passes for a sales jump.

Documents: weekly-<YYYY-MM>, keyed by the month of each week's Monday,
  {"weeks": {"2026-10-12": {"from", "to", "reads": {date: market units added},
                            "market": {"total", "late", "segments"}, "makers": {name: {...}}}}}
"""
from datetime import date, timedelta


def _block_inc(cur, prev, cur_month):
    """cur/prev: segments.build output for one maker (prev may be None) -> increment, or None."""
    if prev is None:
        return None
    inc = {"total": 0, "late": 0, "segments": {}}
    for m, v in cur["total"].items():
        d = v - prev["total"].get(m, 0)
        inc["total"] += d
        if m != cur_month:
            inc["late"] += d
    for s, months in cur["segments"].items():
        old = prev.get("segments", {}).get(s)
        if old is None:
            continue
        inc["segments"][s] = sum(v - old.get(m, 0) for m, v in months.items())
    return inc


def increments(regs, prev_regs, cur_month):
    """regs/prev_regs: {year: {"market", "makers"}} today and as stored by the last run.
    A year or maker the last run did not store is not counted (it would count its whole year)."""
    out = {"market": None, "makers": {}, "skipped": []}

    def add(acc, inc):
        if inc is None:
            return acc
        if acc is None:
            return {"total": inc["total"], "late": inc["late"], "segments": dict(inc["segments"])}
        acc["total"] += inc["total"]
        acc["late"] += inc["late"]
        for s, v in inc["segments"].items():
            acc["segments"][s] = acc["segments"].get(s, 0) + v
        return acc

    for y, cur in regs.items():
        prev = prev_regs.get(y)
        if prev is None:
            out["skipped"].append(f"{y}: no stored year")
            continue
        out["market"] = add(out["market"], _block_inc(cur["market"], prev["market"], cur_month))
        for n, b in cur["makers"].items():
            pb = prev["makers"].get(n)
            if pb is None:
                out["skipped"].append(f"{n} {y}: not stored before")
                continue
            out["makers"][n] = add(out["makers"].get(n), _block_inc(b, pb, cur_month))
    return out


def monday(d):
    return d - timedelta(days=d.weekday())


def doc_id(d):
    return f"weekly-{monday(d):%Y-%m}"


def accumulate(doc, today, inc, source="run"):
    """Add one run's increments to the week holding `today`. Returns the updated doc."""
    doc = doc or {"weeks": {}}
    mon = monday(today)
    w = doc["weeks"].setdefault(mon.isoformat(), {
        "from": mon.isoformat(), "to": (mon + timedelta(days=6)).isoformat(),
        "reads": {}, "market": {"total": 0, "late": 0, "segments": {}}, "makers": {}})

    def add(acc, x):
        acc["total"] += x["total"]
        # late stays unknown (None) for the whole week once any day could not separate it
        acc["late"] = None if acc.get("late") is None or x.get("late") is None else acc["late"] + x["late"]
        for s, v in x["segments"].items():
            acc["segments"][s] = acc["segments"].get(s, 0) + v

    if inc["market"]:
        add(w["market"], inc["market"])
        w["reads"][today.isoformat()] = w["reads"].get(today.isoformat(), 0) + inc["market"]["total"]
    for n, x in inc["makers"].items():
        if x is None:
            continue
        add(w["makers"].setdefault(n, {"total": 0, "late": 0, "segments": {}}), x)
    if source != "run":
        w.setdefault("notes", []).append(source)
    if inc.get("skipped"):
        w.setdefault("skipped", []).extend(f"{today}: {x}" for x in inc["skipped"])
    return doc
