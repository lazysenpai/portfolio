"""Parse a Vahan4 Maker x Month Excel export into {maker: [12 monthly counts]}.

The export (reportTable.xlsx) has a title row, a two-row header whose month labels are
JAN..DEC up to the current month, then one row per maker: S No, maker, months..., TOTAL.
Numbers are strings with Indian digit grouping ("2,31,692"). Header cells are padded
with non-breaking spaces.

Every rule here fails loudly: a layout the parser does not recognise raises, it never
guesses.
"""
import re
import sys
import warnings
import zipfile
from io import BytesIO

import openpyxl

MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
TITLE = re.compile(r"Maker\s+Month\s+Wise\s+Data\s+For\s+(.+?)\s*\((\d{4})\)", re.I)


class LayoutError(ValueError):
    """The file is not the report this parser was written for."""


def _num(cell, where):
    if cell is None or cell == "":
        raise LayoutError(f"empty cell at {where}")
    if isinstance(cell, (int, float)):
        v = cell
    else:
        s = str(cell).replace(",", "").replace("\xa0", "").strip()
        if not re.fullmatch(r"\d+", s):
            raise LayoutError(f"not a whole number at {where}: {cell!r}")
        v = int(s)
    if v < 0 or v != int(v):
        raise LayoutError(f"not a whole number >= 0 at {where}: {cell!r}")
    return int(v)


def parse(content):
    """Return {'scope', 'year', 'months', 'makers': {name: [counts...]}}; raise LayoutError."""
    if not zipfile.is_zipfile(BytesIO(content)):
        raise LayoutError("not an xlsx file (the server may have returned an HTML page)")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wb = openpyxl.load_workbook(BytesIO(content), read_only=True)
    rows = [tuple(r) for r in wb.worksheets[0].iter_rows(values_only=True)]
    if not rows:
        raise LayoutError("empty sheet")

    m = TITLE.search(str(rows[0][0] or ""))
    if not m:
        raise LayoutError(f"unexpected title: {rows[0][0]!r}")
    scope, year = m.group(1).strip(), int(m.group(2))

    head_i = next((i for i, r in enumerate(rows[:10]) if r and "JAN" in [str(c or "").strip() for c in r]), None)
    if head_i is None:
        raise LayoutError("month header row not found")
    labels = [str(c or "").strip() for c in rows[head_i]]
    month_cols = [i for i, c in enumerate(labels) if c in MONTHS]
    months = [labels[i] for i in month_cols]
    if months != MONTHS[: len(months)] or not months:
        raise LayoutError(f"months out of order or missing: {months}")
    total_col = month_cols[-1] + 1

    makers = {}
    for i, r in enumerate(rows[head_i + 1 :], start=head_i + 2):
        if not any(c not in (None, "") for c in r):
            continue
        sno, name = r[0], r[1]
        if sno is None or not str(sno).strip().isdigit():
            raise LayoutError(f"row {i}: expected a serial number, got {sno!r}")
        name = re.sub(r"\s+", " ", str(name or "").replace("\xa0", " ")).strip()
        if not name:
            raise LayoutError(f"row {i}: maker name missing")
        counts = [_num(r[c], f"row {i} {MONTHS[k]}") for k, c in enumerate(month_cols)]
        total = _num(r[total_col], f"row {i} TOTAL")
        if sum(counts) != total:
            raise LayoutError(f"row {i} {name}: months sum to {sum(counts)}, TOTAL says {total}")
        if name in makers:
            raise LayoutError(f"row {i}: maker listed twice: {name}")
        makers[name] = counts
    if not makers:
        raise LayoutError("no maker rows")
    return {"scope": scope, "year": year, "months": months, "makers": makers}


if __name__ == "__main__":
    for path in sys.argv[1:]:
        d = parse(open(path, "rb").read())
        tot = [sum(v[k] for v in d["makers"].values()) for k in range(len(d["months"]))]
        print(path, d["scope"], d["year"], len(d["makers"]), "makers", dict(zip(d["months"], tot)))
