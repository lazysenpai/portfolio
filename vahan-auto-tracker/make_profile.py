"""From the profiling backfill, decide which category groups each maker is fetched in daily.

A group is kept when it carries at least MIN_SHARE of the maker's registrations for the
year. Whatever falls outside the kept groups is reported daily as "other" and warned on
above 3%, so a maker moving into a new segment is seen, not lost.

  python3 make_profile.py 2025   -> maker_groups.json
"""
import json
import os
import sys

from backfill_analytics import path_for, makers, MAIN_GROUPS

ROOT = os.path.dirname(os.path.abspath(__file__))
MIN_SHARE = 0.01


def main(year):
    groups, baseline, report, missing = {}, {}, [], []
    for _, n in makers():
        try:
            total = sum(json.load(open(path_for(year, n, None)))["months"].values())
            by = {g: sum(json.load(open(path_for(year, n, g)))["months"].values()) for g in MAIN_GROUPS}
        except FileNotFoundError:
            missing.append(n)
            continue
        keep = [g for g, v in sorted(by.items(), key=lambda kv: -kv[1]) if total and v / total >= MIN_SHARE]
        groups[n] = keep
        other = 1 - sum(by[g] for g in keep) / total if total else 0
        baseline[n] = round(other, 4)
        report.append((n, total, keep, other))
    if missing:
        raise SystemExit(f"profile incomplete, missing: {missing}")
    json.dump({"_about": f"Category groups fetched daily per maker: each holds >= {MIN_SHARE:.0%} of the maker's {year} registrations.",
               "year": year, "groups": groups,
               "otherBaseline": baseline}, open(os.path.join(ROOT, "maker_groups.json"), "w"), indent=1)
    for n, t, k, o in sorted(report, key=lambda r: -r[1]):
        print(f"{t:>10,}  other {o:5.1%}  {n[:45]:45}  {', '.join(k)}")
    print("requests per day:", 1 + len(MAIN_GROUPS) + sum(1 + len(k) for k in groups.values()))


if __name__ == "__main__":
    main(int(sys.argv[1]))
