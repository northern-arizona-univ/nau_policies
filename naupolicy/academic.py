"""Parsers for the Academic Catalog policy system (www9.nau.edu/policies)."""
from __future__ import annotations

import re
from typing import List, Optional

from bs4 import BeautifulSoup, Tag

from .util import abs_url, norm, parse_date, strip_comments, to_markdown

DETAIL_RE = re.compile(r"/policies/Client/Details/(\d+)")


def index_url(base: str, page: int, pertains_to: Optional[int] = None) -> str:
    if pertains_to is None:
        return f"{base}Client/IndexPaged?page={page}&whoIsLooking=Students&pertainsTo=All"
    return f"{base}Client/IndexPaged?page={page}&whoIsLooking=1&pertainsTo={pertains_to}"


def detail_url(base: str, internal_id: str) -> str:
    return f"{base}Client/Details/{internal_id}"


def parse_index(html: str, url: str) -> List[dict]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    rows = []
    if table is None:
        return rows
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 3:
            continue
        a = tds[1].find("a", href=True)
        if a is None:
            continue
        m = DETAIL_RE.search(a["href"])
        future = []
        if len(tds) > 3:
            for fa in tds[3].find_all("a", href=True):
                fm = DETAIL_RE.search(fa["href"])
                if fm:
                    future.append({"internal_id": fm.group(1), "text": norm(fa.get_text(" "))})
        rows.append({
            "number": norm(tds[0].get_text()),
            "title": norm(a.get_text(" ")),
            "internal_id": m.group(1) if m else None,
            "begin_date_raw": norm(tds[2].get_text()),
            "begin_date": parse_date(tds[2].get_text()),
            "future_versions": future,
        })
    return rows


def _panel_markdown(panel: Tag) -> str:
    # Paragraphs that are only a bold label act as sub-headings in this system.
    for p in panel.find_all("p"):
        strongs = p.find_all(["strong", "b"])
        if len(strongs) == 1 and norm(strongs[0].get_text()) and norm(strongs[0].get_text()) == norm(p.get_text()):
            p.name = "h3"
            strongs[0].unwrap()
    for h in panel.find_all(["h1", "h2"]):
        h.name = "h3"
    return to_markdown(panel)


def _list_after_label(panel: Tag, pattern: str) -> List[str]:
    lab = panel.find(lambda t: t.name in ("p", "h3", "h4") and re.match(pattern, norm(t.get_text()), re.I))
    if lab is None:
        return []
    ul = lab.find_next_sibling(["ul", "ol"])
    if ul is None:
        return []
    return [norm(li.get_text(" ")).rstrip(".") for li in ul.find_all("li")]


def parse_detail(html: str, url: str) -> Optional[dict]:
    soup = BeautifulSoup(html, "html.parser")
    main = soup.select_one("#main")
    if main is None:
        return None
    strip_comments(main)
    rec: dict = {"url": url, "flags": []}
    h2s = [norm(h.get_text(" ")) for h in main.find_all("h2")]
    num_idx = next((i for i, t in enumerate(h2s) if re.fullmatch(r"\d{5,7}", t)), None)
    if num_idx is not None:
        rec["number"] = h2s[num_idx]
        rec["title"] = h2s[num_idx + 1] if num_idx + 1 < len(h2s) else ""
    else:
        rec["flags"].append("no policy number heading found")

    fields = {}
    related = []
    for div in main.find_all("div"):
        span = div.find("span", class_="policy-hdg", recursive=False)
        if span is None or div.find("button", recursive=False) is not None:
            continue
        label = norm(span.get_text()).rstrip(":").strip()
        if label.lower().startswith("related policies"):
            for a in div.find_all("a", href=True):
                related.append({"text": norm(a.get_text(" ")), "url": abs_url(url, a["href"])})
            continue
        value = norm(div.get_text(" "))
        value = norm(value[len(norm(span.get_text())):])
        fields[label] = value
    rec["type"] = fields.pop("Type", None)
    eff = fields.pop("Effective Date", None)
    rec["effective_date"] = parse_date(eff) or eff
    for label, value in fields.items():
        key = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
        if key in ("appeal_eligible", "petition_eligible"):
            rec[key] = value.lower().startswith("y")
        elif key == "fees_may_apply":
            rec[key] = True
        else:
            rec[key] = value or True
    rec["related"] = related

    sections = []
    body_parts = []
    who, entities = [], []
    for btn in main.select("button.accordion"):
        hdg = btn.find("span", class_="policy-hdg")
        name = norm(hdg.get_text()) if hdg else norm(btn.get_text())
        panel = btn.find_next_sibling("div", class_="panel")
        if panel is None:
            continue
        if not who:
            who = _list_after_label(panel, r"^who should know")
        if not entities:
            entities = _list_after_label(panel, r"^entities affected")
        sections.append(name)
        body_parts.append(f"## {name}\n\n" + _panel_markdown(panel))
    rec["sections"] = sections
    rec["who_should_know"] = who
    rec["entities_affected"] = entities
    rec["body_md"] = "\n".join(body_parts)
    rec["main_html"] = str(main)
    if not body_parts:
        rec["flags"].append("no policy text sections found")
    return rec
