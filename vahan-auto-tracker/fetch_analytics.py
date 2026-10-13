"""Monthly registration counts from the Parivahan analytics public dashboard (the
successor to Vahan4), one maker name and optional category group per request.

GET /analytics/publicdashboard/vahandashboard/durationWiseRegistrationTable
returns [{"yearAsString": "2026-October", "registeredVehicleCount": 26074}, ...],
newest month first, for one calendar year. Filters are jQuery-style arrays
(vehicleMakers[]=..., vehicleCategoryGroup[]=...). rtoCode and fitnessCheck must be
"0", not empty, or the server answers 400. The active-compliant and
active-non-compliant archive flags are the page's own defaults.

Usage: python3 fetch_analytics.py YEAR [MAKER] [--group "Four Wheeler"]
"""
import argparse
import json
import time

import requests

URL = "https://analytics.parivahan.gov.in/analytics/publicdashboard/vahandashboard/durationWiseRegistrationTable"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128 Safari/537.36"
MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]
GROUPS = ["Two Wheeler", "Three Wheeler", "Four Wheeler", "Goods Vehicle", "Bus", "Tractor",
          "Construction Equipment Vehicle", "Public Service Vehicle", "Special Category Vehicles",
          "Trailer", "Ambulance/Hearses"]


class SourceError(RuntimeError):
    """The source answered with something other than the expected monthly table."""


def params(year, maker=None, group=None):
    p = [("stateCode", ""), ("rtoCode", "0"), ("toYear", str(year)), ("fromYear", str(year)),
         ("calendarType", "3"), ("timePeriod", "0"), ("fitnessCheck", "0"), ("vehicleType", ""),
         ("archiveTypeAC", "ACTIVE_COMPLIANT"), ("archiveTypeANC", "ACTIVE_NON_COMPLIANT"),
         ("archiveTypePA", ""), ("archiveTypeTA", ""), ("archiveTypeNA", "")]
    if maker:
        p.append(("vehicleMakers[]", maker))
    for g in ([group] if isinstance(group, str) else (group or [])):
        if g not in GROUPS:
            raise ValueError(f"unknown category group: {g}")
        p.append(("vehicleCategoryGroup[]", g))        # several groups -> their union
    return p


def fetch(year, maker=None, group=None, session=None, tries=3):
    """Return {"YYYY-MM": count} for every month the source reports; raise SourceError.
    group may be one group name or a list, whose union is counted."""
    s = session or requests.Session()
    last = None
    for attempt in range(tries):
        try:
            r = s.get(URL, params=params(year, maker, group), timeout=60,
                      headers={"User-Agent": UA, "X-Requested-With": "XMLHttpRequest"})
            if r.status_code != 200:
                raise SourceError(f"HTTP {r.status_code}")
            try:
                rows = r.json()
            except ValueError:
                raise SourceError("not JSON: " + r.text[:120])
            return to_months(rows, year)
        except (requests.RequestException, SourceError) as e:
            last = e
            time.sleep(2 * (attempt + 1))
    raise SourceError(f"{maker or 'all makers'} {group or ''} {year}: {last}")


def to_months(rows, year):
    if not isinstance(rows, list):
        raise SourceError(f"expected a list, got {type(rows).__name__}")
    out = {}
    for row in rows:
        label, count = row.get("yearAsString"), row.get("registeredVehicleCount")
        try:
            y, name = label.split("-", 1)
            key = f"{int(y)}-{MONTHS.index(name) + 1:02d}"
        except (AttributeError, ValueError):
            raise SourceError(f"unexpected month label: {label!r}")
        if int(y) != year:
            raise SourceError(f"asked for {year}, got {label}")
        if not isinstance(count, int) or count < 0:
            raise SourceError(f"{label}: count is not a whole number >= 0: {count!r}")
        if key in out:
            raise SourceError(f"{label} reported twice")
        out[key] = count
    return dict(sorted(out.items()))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("year", type=int)
    ap.add_argument("maker", nargs="?")
    ap.add_argument("--group")
    a = ap.parse_args()
    print(json.dumps(fetch(a.year, a.maker, a.group), indent=1))
