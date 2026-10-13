"""Parsers for the University Policy Library (in.nau.edu/university-policy-library)."""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from bs4 import BeautifulSoup, Tag

from .util import (FILE_RE, abs_url, demote_headings, norm, parse_date, slugify,
                   strip_comments, to_markdown)

LANDING_RE = re.compile(r"^https?://in\.nau\.edu/university-policy-library/([^/?#]+)/?(?:[?#].*)?$")

META_LABELS = {
    "responsible executive": "responsible_executive",
    "policy owner": "responsible_executive",
    "responsible office": "responsible_office",
    "effective date": "effective_date",
    "origination date": "effective_date",
    "last revised": "last_revised",
    "revision date(s)": "last_revised",
    "revision dates": "last_revised",
    "revision date": "last_revised",
    "revised": "last_revised",
    "contact": "contact",
}
META_RE = re.compile(r"(Responsible Executive|Policy Owner|Responsible Office|Effective Date|Origination Date|Last Revised|Revision date)\s*(\(s\))?\s*:", re.I)
META_SPLIT_RE = re.compile(r"\s+(?=(Responsible Executive|Policy Owner|Responsible Office|Effective Date|Origination Date|"
                           r"Last Revised|Revision date\(s\)|Revision dates?|Contact)\s*:)", re.I)
ANY_DATE_RE = re.compile(r"\d{1,2}/\d{1,2}/\d{2,4}|[A-Z][a-z]+\.? \d{1,2},? \d{4}")
ROLE_ORDER = {"policy": 0, "procedure": 1, "draft": 2, "document": 3, "printable": 4}
VIEW_RE = re.compile(r"^\s*(click here to )?view\b|^\s*existing policy\b", re.I)


def _collect_page_links(container: Optional[Tag], base: str) -> List[dict]:
    """'View the Policy' style links that point at a web page instead of a file."""
    out, seen = [], set()
    if container is None:
        return out
    for a in container.find_all("a", href=True):
        url = abs_url(base, a["href"])
        text = norm(a.get_text(" "))
        if FILE_RE.search(url) or url in seen or not text or not VIEW_RE.search(text):
            continue
        if url.startswith(("mailto:", "javascript:")) or LANDING_RE.match(url):
            continue
        seen.add(url)
        out.append({"url": url, "title": text, "role": _file_role(text) if _file_role(text) != "document" else "policy",
                    "location": "body", "link_type": "page"})
    return out


def landing_slug(url: str, non_policy) -> Optional[str]:
    m = LANDING_RE.match(url or "")
    if not m:
        return None
    slug = m.group(1)
    if slug in non_policy or slug.startswith("wp-"):
        return None
    return slug


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def _columns(soup: BeautifulSoup) -> Tuple[Optional[Tag], Optional[Tag], Optional[Tag]]:
    ec = soup.select_one(".entry-content") or soup.select_one("main")
    if ec is None:
        return None, None, None
    left = ec.select_one(".left-column") or ec
    right = ec.select_one(".right-column")
    return ec, left, right


def page_title(soup: BeautifulSoup) -> str:
    og = soup.find("meta", property="og:title")
    t = og["content"] if og and og.get("content") else (soup.title.get_text() if soup.title else "")
    return norm(re.sub(r"\s+-\s+University Policy Library\s*$", "", t))


def main_html(html: str) -> str:
    """The part of the page worth archiving (drops site chrome)."""
    soup = _soup(html)
    ec, _, _ = _columns(soup)
    return str(ec) if ec is not None else html


# --------------------------------------------------------------------------- manuals / indexes

def parse_manual(html: str, url: str) -> Tuple[str, List[dict]]:
    """Return (manual title, [{text, url, group}]) for links in a manual page body."""
    soup = _soup(html)
    title = page_title(soup)
    _, left, _ = _columns(soup)
    entries = []
    if left is None:
        return title, entries
    for a in left.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("mailto:", "#", "javascript:")):
            continue
        heading = a.find_previous(["h2", "h3", "h4"])
        group = norm(heading.get_text(" ")) if heading is not None and left in heading.parents else None
        if group and group.lower() == title.lower():
            group = None
        entries.append({"text": norm(a.get_text(" ")), "url": abs_url(url, href), "group": group})
    return title, entries


def parse_home(html: str, url: str) -> Dict[str, list]:
    """Manual links from the nav/body and the 'Recent Policy Changes' list."""
    soup = _soup(html)
    out = {"manual_slugs": [], "recent_changes": []}
    for a in soup.find_all("a", href=True):
        m = LANDING_RE.match(abs_url(url, a["href"]))
        if m and a.find_parent(["nav", "header"]) is not None:
            out["manual_slugs"].append(m.group(1))
    heading = soup.find(lambda t: t.name in ("h2", "h3", "h4") and "recent policy changes" in norm(t.get_text()).lower())
    if heading is not None:
        ul = heading.find_next("ul")
        if ul is not None:
            for li in ul.find_all("li", recursive=False):
                a = li.find("a", href=True)
                out["recent_changes"].append({
                    "text": norm(li.get_text(" ")),
                    "url": abs_url(url, a["href"]) if a else None,
                })
    return out


def parse_by_subject(html: str, url: str) -> List[dict]:
    """Every entry of the A-Z subject index: {letter, term, url}."""
    soup = _soup(html)
    _, left, _ = _columns(soup)
    rows = []
    if left is None:
        return rows
    for li in left.find_all("li"):
        heading = li.find_previous(["h2", "h3", "h4", "h5"])
        letter = norm(heading.get_text()) if heading is not None else ""
        if len(letter) != 1:
            continue  # skip nav/quick-link lists
        a = li.find("a", href=True)
        rows.append({
            "letter": letter,
            "term": norm(li.get_text(" ")),
            "url": abs_url(url, a["href"]) if a else None,
        })
    return rows


def page_markdown(html: str) -> str:
    soup = _soup(html)
    _, left, _ = _columns(soup)
    if left is None:
        return ""
    strip_comments(left)
    return to_markdown(left)


# --------------------------------------------------------------------------- landing pages

def _file_role(text: str) -> str:
    t = text.lower()
    if "draft" in t or "proposed" in t or "redline" in t:
        return "draft"
    if "printable" in t:
        return "printable"
    if "procedure" in t:
        return "procedure"
    if re.search(r"\bview\b.*\bpolic", t) or t in ("view policy", "policy"):
        return "policy"
    return "document"


def _collect_files(container: Optional[Tag], base: str, location: str, files: Dict[str, dict]) -> None:
    if container is None:
        return
    for a in container.find_all("a", href=True):
        url = abs_url(base, a["href"])
        if not FILE_RE.search(url):
            continue
        text = norm(a.get_text(" "))
        role = _file_role(text) if text else None   # empty anchors (button wrappers) say nothing
        cur = files.get(url)
        if cur is None:
            files[url] = {"url": url, "title": text, "role": role, "location": location}
        else:
            if not cur["title"] and text:
                cur["title"] = text
            if role and (cur["role"] is None or ROLE_ORDER[role] < ROLE_ORDER[cur["role"]]):
                cur["role"] = role
            if location == "body":
                cur["location"] = "body"


def _finish_roles(files: Dict[str, dict]) -> None:
    for f in files.values():
        if f["role"] is None:
            f["role"] = "document"


def _section_after(h: Tag) -> List[Tag]:
    out = []
    for sib in h.find_next_siblings():
        if sib.name in ("h2", "h3", "h4"):
            break
        out.append(sib)
    return out


def _list_after(left: Tag, pattern: str) -> List[str]:
    h = left.find(lambda t: t.name in ("h4", "h3") and re.match(pattern, norm(t.get_text()), re.I))
    if h is None:
        return []
    items = []
    for el in _section_after(h):
        for li in el.find_all("li") if el.name in ("ul", "ol") else []:
            items.append(norm(li.get_text(" ")))
    return items


def _official_number(slug: str, title: str) -> Optional[str]:
    m = re.match(r"^(\d\.\d{2}(?:\(\d\))?)\s", title)
    if m:
        return "HR " + m.group(1)
    m = re.match(r"^(TRV|CMP|PCC)\s*(\d+)", title)
    if m:
        return f"{m.group(1)} {m.group(2)}"
    m = re.match(r"^hr_(\d)-(\d+)$", slug)
    if m:
        a, b = m.groups()
        if len(b) == 3 and b[2] != "0":          # hr_4-051 -> 4.05(1)
            return f"HR {a}.{b[:2]}({b[2]})"
        return f"HR {a}.{b[:2]}" + (f".{b[2:]}" if len(b) > 2 else "")
    return None


def parse_landing(html: str, url: str, slug: str, snapshot_date: str, bundle: bool = False) -> Optional[dict]:
    soup = _soup(html)
    ec, left, right = _columns(soup)
    if left is None:
        return None
    strip_comments(ec)
    rec: dict = {
        "slug": slug,
        "url": url,
        "title": page_title(soup),
        "status": "active",
        "flags": [],
    }

    # Files first, before we start removing elements.
    files: Dict[str, dict] = {}
    _collect_files(left, url, "body", files)
    _collect_files(right, url, "sidebar", files)
    _finish_roles(files)
    page_links = _collect_page_links(left, url)
    left_text = norm(left.get_text(" "))
    if re.search(r"\bdraft replacement\b|\bdraft\b.{0,40}\bopen for (public )?comment", left_text, re.I):
        rec["draft_noted"] = True
    m = re.search(r"(has been|is now|now) (archived|superseded)", left_text, re.I)
    if m:
        rec["status"] = "superseded"
        for a in left.find_all("a", href=True):
            s = landing_slug(abs_url(url, a["href"]), set())
            if s and s != slug:
                rec["superseded_by"] = "upl/" + s
                break

    # Manual label (first h5) and title (first h3)
    h3 = left.find("h3")
    h5 = left.find("h5")
    if h5 is not None and h3 is not None and h5 in h3.find_all_previous("h5"):
        rec["manual_label"] = norm(h5.get_text(" "))
        h5.decompose()
    if h3 is not None:
        t = norm(h3.get_text(" "))
        if t:
            rec["title"] = t
        h3.decompose()
    if re.search(r"\(interim\)", rec["title"], re.I):
        rec["status"] = "interim"
        rec["title"] = norm(re.sub(r"\(interim\)", "", rec["title"], flags=re.I))
    if any(re.search(r"interim polic", f["title"], re.I) for f in files.values()):
        rec["status"] = "interim"

    # Metadata block(s)
    meta: Dict[str, str] = {}
    raw_labels: Dict[str, str] = {}
    for p in left.find_all("p", limit=10):
        if not META_RE.search(p.get_text(" ")):
            continue
        mail = p.find("a", href=re.compile(r"^mailto:", re.I))
        if mail:
            rec["contact_email"] = mail["href"].split(":", 1)[1].split("?")[0]
        for br in p.find_all("br"):
            br.replace_with("\n")
        key = None
        for line in META_SPLIT_RE.sub("\n", p.get_text("")).split("\n"):
            m = re.match(r"\s*([A-Za-z ()]{3,40}?)\s*:\s*(.*)$", line)
            if m and m.group(1).strip().lower() in META_LABELS:
                key = META_LABELS[m.group(1).strip().lower()]
                raw_labels[key] = m.group(1).strip()
                meta[key] = norm(m.group(2))
            elif m and len(m.group(1).split()) <= 4:
                key = "meta_" + slugify(m.group(1)).replace("-", "_")
                meta[key] = norm(m.group(2))
            elif key and norm(line):
                meta[key] = norm(meta[key] + " " + line)
        p.decompose()
    for k, v in meta.items():
        if k in ("effective_date", "last_revised"):
            iso = parse_date(v)
            if iso is None:
                found = [d for d in (parse_date(x) for x in ANY_DATE_RE.findall(v)) if d]
                if found:  # e.g. "1/1/2010, 11/10/2022" -> latest
                    iso = max(found) if k == "last_revised" else min(found)
                    rec[k + "_as_published"] = v
            rec[k] = iso or v
            if iso is None and v and not re.match(r"(not applicable|n/?a|see )", v, re.I):
                rec["flags"].append(f"unparsed {k}: {v!r}")
        else:
            rec[k] = v
    if raw_labels.get("effective_date", "").lower().startswith("origination"):
        rec["effective_date_label"] = "Origination Date"

    # Keywords
    kh = left.find(lambda t: t.name in ("h5", "h4") and norm(t.get_text()).lower().startswith("keywords"))
    if kh is not None:
        kws = []
        for sib in _section_after(kh):
            if sib.name == "p":
                for br in sib.find_all("br"):
                    br.replace_with("\n")
                kws += [norm(x) for x in sib.get_text("").split("\n") if norm(x)]
            sib.decompose()
        kh.decompose()
        if kws:
            rec["keywords"] = kws

    # Printable-PDF buttons (duplicate of page text)
    for a in list(left.find_all("a", href=True)):
        if a.parent is None or "printable" not in a.get_text(" ").lower():
            continue
        rec.setdefault("printable_pdf", abs_url(url, a["href"]))
        top = a
        while top.parent is not None and top.parent is not left:
            top = top.parent
        if top.parent is left and len(norm(top.get_text(" "))) < 80:
            top.decompose()
        else:
            a.decompose()
    # left-over empty shortcode button anchors
    for a in list(left.find_all("a", href=True)):
        if a.parent is not None and not norm(a.get_text(" ")) and FILE_RE.search(a["href"]):
            a.decompose()

    # Structured lists
    rec["entities_affected"] = _list_after(left, r"^entities affected")
    rec["who_should_know"] = _list_after(left, r"^who should know")

    # Related information links
    related = []
    rh = left.find(lambda t: t.name == "h4" and norm(t.get_text()).lower().startswith("related information"))
    if rh is not None:
        for el in _section_after(rh):
            for a in el.find_all("a", href=True):
                related.append({"text": norm(a.get_text(" ")), "url": abs_url(url, a["href"])})
    rec["related"] = related

    # Policy history
    history = []
    hh = left.find(lambda t: t.name == "h4" and norm(t.get_text()).lower().startswith("policy history"))
    if hh is not None:
        for el in _section_after(hh):
            for br in el.find_all("br"):
                br.replace_with("\n")
            for line in el.get_text("").split("\n"):
                m = re.match(r"\s*(\d{1,2}/\d{1,2}/\d{2,4})\s*[:\-–—]?\s*(.*)$", line)
                if m:
                    history.append({"date": parse_date(m.group(1)) or m.group(1), "note": norm(m.group(2))})
    rec["history"] = history
    for h in history:
        if re.match(r"\d{4}-\d{2}-\d{2}$", h["date"]) and h["date"] > snapshot_date:
            rec["flags"].append(f"history date in the future: {h['date']} ({h['note']})")
    lr = rec.get("last_revised")
    revised = [h["date"] for h in history if re.search(r"revis|amend|updat", h["note"], re.I)]
    if lr and revised and re.match(r"\d{4}-", lr) and lr not in revised:
        rec["flags"].append(f"Last Revised {lr} not found in policy history")

    # Sections (template h4 headings)
    rec["sections"] = [norm(h.get_text(" ")) for h in left.find_all("h4")
                       if norm(h.get_text(" ")) and not re.match(r"view\b", norm(h.get_text(" ")), re.I)]

    rec["official_number"] = _official_number(slug, rec["title"])

    # Bundle children
    if bundle:
        rec["children"] = parse_bundle_children(left, url)

    # Body markdown ("View the Policy" buttons are links, not section headings)
    for h in left.find_all(["h4", "h5"]):
        if re.match(r"view\b", norm(h.get_text(" ")), re.I):
            h.name = "p"
    demote_headings(left, {"h4": "h2", "h5": "h3", "h6": "h4"})
    body = to_markdown(left)
    rec["body_md"] = body
    body_len = len(norm(re.sub(r"[#*_>\-\[\]()]", " ", body)))
    lower_sections = [s.lower() for s in rec["sections"]]
    has_template_body = any(s in ("policy", "policy statement") or s.startswith("policy statement") for s in lower_sections)

    rec["documents"] = sorted(list(files.values()) + page_links,
                              key=lambda f: (ROLE_ORDER[f["role"]], f["location"] != "body"))
    body_docs = [f for f in rec["documents"] if f["location"] == "body"]
    has_policy_link = any(f["role"] == "policy" for f in body_docs)
    if bundle:
        rec["kind"] = "bundle"
    elif has_template_body:
        rec["kind"] = "full_text"
    elif has_policy_link:
        rec["kind"] = "summary"
    elif body_len > 1500 or not body_docs:
        # Older pages (e.g. HR 5.15 Dress Code) carry the whole policy as plain page text.
        rec["kind"] = "full_text" if body_len > 300 else "stub"
        if rec["kind"] == "stub":
            rec["flags"].append("page has almost no text and no policy link")
    else:
        # Short page whose policy file link is titled with the policy name, or only a printable PDF
        rec["kind"] = "summary"
        cand = next((f for f in body_docs if f["role"] in ("document", "printable") and f.get("link_type") != "page"), None)
        if cand is None and rec.get("printable_pdf"):
            cand = {"url": rec["printable_pdf"], "title": "Printable PDF", "role": "printable", "location": "body"}
            rec["documents"].insert(0, cand)
        if cand is not None:
            cand["role"] = "policy"
            cand["role_inferred"] = True
        elif any(f["role"] == "draft" for f in body_docs):
            rec["flags"].append("only a DRAFT policy document is linked; current policy text is the page summary only")
            rec["draft_only"] = True
        else:
            rec["flags"].append("summary page with no policy document link")
    if rec.get("draft_noted") and not any(f["role"] == "draft" for f in rec["documents"]):
        rec["flags"].append("page mentions a draft replacement policy (not linked)")
    rec["body_chars"] = body_len
    return rec


def parse_bundle_children(left: Tag, url: str) -> List[dict]:
    """List items on bundle pages (Comptroller, Travel, Contracting) -> child policies."""
    children = []
    section = None
    subgroup = None
    seen = set()
    for el in left.find_all(["h4", "li"]):
        if el.name == "h4":
            section = norm(el.get_text(" "))
            subgroup = None
            ha = el.find("a", href=True)
            if ha is not None and norm(ha.get_text(" ")):
                # A whole section published as one document, e.g. "Section 535. Lodging" -> PDF
                link_url = abs_url(url, ha["href"])
                if link_url not in seen:
                    seen.add(link_url)
                    m = re.match(r"^Section\s+(\d+)\.?\s*(.*)$", section, re.I)
                    children.append({
                        "code": m.group(1) if m else None,
                        "title": norm(m.group(2)) if m else section,
                        "section": section, "subgroup": None, "url": link_url,
                        "link_type": "file" if FILE_RE.search(link_url) else ("landing" if LANDING_RE.match(link_url) else "link"),
                    })
            continue
        own_text = norm(" ".join(t for t in el.find_all(string=True) if t.find_parent("li") is el))
        a = next((x for x in el.find_all("a", href=True) if x.find_parent("li") is el), None)
        if a is None:
            if own_text:
                subgroup = own_text
            continue
        link_url = abs_url(url, a["href"])
        if link_url in seen:
            continue
        seen.add(link_url)
        m = re.match(r"^((?:[A-Z]{2,4}\s*)?\d{1,3}(?:[-–.]\d+)*)\.?\s+(.*)$", own_text)
        code, title = (m.group(1), m.group(2)) if m else (None, own_text)
        children.append({
            "code": code.replace("–", "-") if code else None,
            "title": norm(title) or norm(a.get_text(" ")),
            "section": section,
            "subgroup": subgroup,
            "url": link_url,
            "link_type": "file" if FILE_RE.search(link_url) else ("landing" if LANDING_RE.match(link_url) else "link"),
        })
    return children
