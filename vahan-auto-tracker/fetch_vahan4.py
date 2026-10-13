"""Spike: replay the Vahan4 dashboard's Maker x Month report and its Excel export.

Recipe captured in the browser on 2026-10-09:
  GET  reportview.xhtml                      -> session cookie + ViewState + field names
  POST the form, y=Maker, x=Month Wise, year, optional VhClass ids, + the main Refresh button
  POST the form again with groupingTable:xls -> the Excel file

Usage: python3 fetch_vahan4.py [YEAR] [VHCLASS_ID ...]
"""
import hashlib, re, sys, time
import requests
from bs4 import BeautifulSoup

BASE = "https://vahan.parivahan.gov.in/vahan4dashboard/vahan/view/reportview.xhtml"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128 Safari/537.36"


def form_fields(html):
    """Every successful-control value the browser would send, keyed in page order."""
    soup = BeautifulSoup(html, "html.parser")
    form = soup.find("form", id="masterLayout_formlogin")
    if form is None:
        raise RuntimeError("report form not found: the page has changed")
    fields = []
    for el in form.find_all(["input", "select"]):
        name = el.get("name")
        if not name:
            continue
        if el.name == "select":
            opt = el.find("option", selected=True) or el.find("option")
            fields.append((name, opt.get("value", "") if opt else ""))
        elif el.get("type") in ("checkbox", "radio"):
            if el.has_attr("checked"):
                fields.append((name, el.get("value", "on")))
        elif el.get("type") not in ("submit", "button", "image"):
            fields.append((name, el.get("value", "")))
    return soup, form, fields


def refresh_button(soup):
    """The Refresh whose update list covers the grouping table (the main one)."""
    for b in soup.find_all("button"):
        if "Refresh" in b.get_text() and "groupingTable" in (b.get("onclick") or ""):
            return b["id"]
    raise RuntimeError("main Refresh button not found")


def set_field(fields, name, value):
    out = [(k, v) for k, v in fields if k != name]
    out.append((name, value))
    return out


def fetch(year, vhclass_ids):
    s = requests.Session()
    s.headers["User-Agent"] = UA
    r = s.get(BASE, timeout=60)
    r.raise_for_status()
    soup, form, fields = form_fields(r.text)
    action = requests.compat.urljoin(BASE, form["action"])
    btn = refresh_button(soup)

    fields = set_field(fields, "yaxisVar_input", "Maker")
    fields = set_field(fields, "xaxisVar_input", "Month Wise")
    fields = set_field(fields, "selectedYearType_input", "C")
    fields = set_field(fields, "selectedYear_input", str(year))
    fields = set_field(fields, "j_idt29_input", "A") if any(k == "j_idt29_input" for k, _ in fields) else fields
    fields = [(k, v) for k, v in fields if k != "VhClass"] + [("VhClass", str(c)) for c in vhclass_ids]
    fields.append((btn, ""))

    r2 = s.post(action, data=fields, timeout=120, headers={"Referer": BASE})
    r2.raise_for_status()
    soup2, form2, fields2 = form_fields(r2.text)
    title = soup2.find(string=re.compile(r"Month Wise Data For"))
    action2 = requests.compat.urljoin(BASE, form2["action"])
    fields2.append(("groupingTable:xls", "groupingTable:xls"))

    r3 = s.post(action2, data=fields2, timeout=180, headers={"Referer": BASE})
    r3.raise_for_status()
    return {
        "title": title.strip() if title else None,
        "ctype": r3.headers.get("content-type"),
        "disposition": r3.headers.get("content-disposition"),
        "bytes": len(r3.content),
        "sha256": hashlib.sha256(r3.content).hexdigest(),
        "content": r3.content,
    }


if __name__ == "__main__":
    year = int(sys.argv[1]) if len(sys.argv) > 1 else time.localtime().tm_year
    classes = sys.argv[2:]
    t0 = time.time()
    res = fetch(year, classes)
    out = f"vahan4_{year}_{'-'.join(classes) or 'all'}.bin"
    with open(out, "wb") as f:
        f.write(res.pop("content"))
    res["seconds"] = round(time.time() - t0, 1)
    res["saved"] = out
    print(res)
