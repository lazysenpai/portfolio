"""Segments built so that no vehicle is counted twice.

The dashboard's category groups overlap: a minibus can be both "Bus" and "Four Wheeler",
a pickup both "Goods Vehicle" and "Four Wheeler". A request listing several groups
returns their union, so each segment is fetched as a union and the passenger segment is
derived by subtraction:

  2W   = Two Wheeler
  3W   = Three Wheeler
  TRAC = Tractor
  CV   = Goods Vehicle ∪ Bus ∪ Ambulance/Hearses   (a four-wheeled bus or pickup is CV, as in FADA)
  PV   = (Four Wheeler ∪ Goods Vehicle ∪ Bus ∪ Ambulance/Hearses) − CV

FADA counts ambulances and hearses as CV; leaving them out put Maruti's CV 15% and Force's
23% under FADA's (2026-10-10). The group is disjoint from the four-wheeler block (block ∪
ambulances = block + ambulances for Maruti, Force, SML) but not from Three Wheeler: a three-
wheeled ambulance is in both (Mahindra Last Mile, 13 in Oct 2024). So for a maker that sells
three-wheelers, and for the market, CV and the block are fetched with Three Wheeler in the
union and the three-wheelers subtracted again:

  CV   = (Goods ∪ Bus ∪ Ambulance ∪ Three Wheeler) − Three Wheeler
  PV   = (Four Wheeler ∪ Goods ∪ Bus ∪ Ambulance ∪ Three Wheeler) − Three Wheeler − CV

PV and CV cannot double-count: PV is the block minus CV, so the two add back to the block
exactly. Overlap can only arise between blocks fetched independently (2W, 3W, TRAC and the
four-wheeler block). For a maker in two or more such blocks, the union of its own groups
is fetched too ("own"): the segments must add up to it, which proves no vehicle sits in
two of them. Registrations outside the maker's own groups are its "outside" share.
"""
SINGLE = {"2W": ["Two Wheeler"], "3W": ["Three Wheeler"], "TRAC": ["Tractor"]}
AMB = "Ambulance/Hearses"
CV = ["Goods Vehicle", "Bus", AMB]
BLOCK = ["Four Wheeler", "Goods Vehicle", "Bus", AMB]
# every group a segment draws on, in the order requests list them
ALL6 = ["Two Wheeler", "Three Wheeler", "Four Wheeler", "Goods Vehicle", "Bus", AMB, "Tractor"]
ORDER = ["2W", "3W", "PV", "CV", "TRAC"]
LABEL = {"2W": "Two-wheelers", "3W": "Three-wheelers", "PV": "Passenger vehicles",
         "CV": "Commercial vehicles", "TRAC": "Tractors"}


def cv_req(segs):
    return CV + SINGLE["3W"] if "3W" in segs else CV


def block_req(segs):
    return BLOCK + SINGLE["3W"] if "3W" in segs else BLOCK


def segments_of(groups):
    """The segments a maker sells in, from its profiled groups."""
    s = set()
    for g in groups:
        s |= {k for k, v in SINGLE.items() if g in v}
        if g in CV:
            s.add("CV")
        if g == "Four Wheeler":
            s.add("PV")
    return [k for k in ORDER if k in s]


def blocks_of(segs):
    """Independently fetched blocks: each single group, and the four-wheeler block."""
    b = [SINGLE[k] for k in segs if k in SINGLE]
    if "PV" in segs:
        b.append(BLOCK)
    elif "CV" in segs:
        b.append(CV)
    return b


def own_groups(segs):
    return sorted({g for blk in blocks_of(segs) for g in blk}, key=ALL6.index)


def requests_for(segs):
    """The group lists to fetch (each one request) for a maker in these segments, plus the total."""
    out = [None]                                   # None = the maker's total, no group filter
    for k in segs:
        if k in SINGLE:
            out.append(SINGLE[k])
    if "CV" in segs or "PV" in segs:
        out.append(cv_req(segs))                   # PV needs CV to subtract
    if "PV" in segs:
        out.append(block_req(segs))
    if len(blocks_of(segs)) > 1:
        out.append(own_groups(segs))               # proves the blocks do not overlap
    return out


def key(groups):
    return None if groups is None else "+".join(groups)


def build(fetched, segs):
    """fetched: {key(groups): {month: count}} -> {"total", "segments": {seg: {month: n}}, "covered", ["own"]}"""
    total = fetched[None]
    months = sorted(total)
    out = {"total": total, "segments": {}}
    for k in segs:
        if k in SINGLE:
            out["segments"][k] = fetched[key(SINGLE[k])]
        elif k in ("CV", "PV"):
            w3 = fetched[key(SINGLE["3W"])] if "3W" in segs else {}
            less3 = lambda d: {m: d[m] - w3.get(m, 0) for m in d}
            cv = less3(fetched[key(cv_req(segs))])
            if k == "CV":
                out["segments"]["CV"] = cv
            else:
                blk = less3(fetched[key(block_req(segs))])
                out["segments"]["PV"] = {m: blk.get(m, 0) - cv.get(m, 0) for m in months if m in blk}
    blocks = blocks_of(segs)
    if len(blocks) > 1:
        out["own"] = fetched[key(own_groups(segs))]
        out["covered"] = out["own"]
    elif blocks:
        out["covered"] = fetched[key(blocks[0])]
    else:
        out["covered"] = {m: 0 for m in months}
    return out
