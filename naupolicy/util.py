"""Small shared helpers: text cleanup, dates, HTML -> Markdown."""
from __future__ import annotations

import datetime as _dt
import hashlib
import re
from typing import Optional
from urllib.parse import urljoin, urlparse, unquote

from bs4 import Comment
from markdownify import markdownify

FILE_RE = re.compile(r"\.(pdf|docx?|xlsx?|pptx?)(?:[?#].*)?$", re.I)


def norm(s: Optional[str]) -> str:
    """Collapse whitespace (incl. non-breaking spaces)."""
    if not s:
        return ""
    return re.sub(r"\s+", " ", s.replace("\xa0", " ")).strip()


def sha256(data) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def slugify(s: str, maxlen: int = 60) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s[:maxlen].rstrip("-") or "item"


def abs_url(base: str, href: str) -> str:
    return urljoin(base, href.strip())


def file_ext(url: str) -> Optional[str]:
    m = FILE_RE.search(url)
    return m.group(1).lower() if m else None


def file_stem(url: str) -> str:
    name = unquote(urlparse(url).path.rsplit("/", 1)[-1])
    return re.sub(r"\.[A-Za-z0-9]+$", "", name)


DATE_FORMATS = ("%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d")


def parse_date(s: Optional[str]) -> Optional[str]:
    """Return ISO date for common NAU date formats, else None."""
    if not s:
        return None
    s = norm(s).rstrip(".")
    s = re.sub(r"(\d)(st|nd|rd|th),", r"\1,", s)
    s = s.replace("Sept ", "Sep ")
    for fmt in DATE_FORMATS:
        try:
            return _dt.datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def strip_comments(tag) -> None:
    for c in tag.find_all(string=lambda t: isinstance(t, Comment)):
        c.extract()


def to_markdown(html) -> str:
    md = markdownify(str(html), heading_style="ATX", bullets="-",
                     strip=["img", "script", "style", "button", "svg", "iframe", "form", "input"])
    md = md.replace("\xa0", " ")
    md = re.sub(r"\[\s*\]\([^)]*\)", "", md)          # empty links
    md = re.sub(r"^#+\s*$", "", md, flags=re.M)         # empty headings
    md = re.sub(r"\*\*\s*\*\*", "", md)                 # empty bold
    md = re.sub(r"[ \t]+\n", "\n", md)
    md = re.sub(r"\n{3,}", "\n\n", md)
    return md.strip() + "\n"


def demote_headings(tag, mapping) -> None:
    """Rename heading tags in place, e.g. {'h4': 'h2', 'h5': 'h3'}."""
    for old, new in mapping.items():
        for h in tag.find_all(old):
            h.name = "__" + new
    for h in tag.find_all(lambda t: t.name and t.name.startswith("__")):
        h.name = h.name[2:]


BULLET_RE = re.compile(r"^[▪•●◦■□➢►✓•▪‣o]\s+")
LIST_START_RE = re.compile(r"^([▪•●◦■□➢►\-–]|\(?[0-9]{1,2}[.)]|\(?[a-zA-Z][.)]|[IVX]{1,4}\.)\s")


ACRONYMS = {"NAU", "ABOR", "COFS", "SOE", "FSC", "ARC", "NCAA", "VA", "FERPA", "ADA", "IT", "ITS", "HR", "US", "U.S.",
            "TT", "NTT", "PI", "IRB", "FMLA", "FLSA", "WUE", "WRGP", "WICHE", "GPA", "UCC", "CACC", "LOUIE", "DOD", "EEO",
            "AZ", "ARS", "A.R.S.", "FAQ", "FTE", "OCRC", "CERT", "MOU", "MOA", "RCR", "COI"}


def _is_caps_heading(s: str) -> bool:
    letters = [c for c in s if c.isalpha()]
    if len(letters) < 3 or len(s) > 90 or s.endswith((",", ";")) or re.search(r"\.{4,}", s):
        return False
    upper = sum(1 for c in letters if c.isupper())
    return upper / len(letters) >= 0.95 and not re.search(r"\d{3,}", s)


def _heading_text(s: str) -> str:
    small = {"a", "an", "and", "as", "at", "by", "for", "in", "of", "on", "or", "the", "to", "with"}
    words = s.rstrip(":").split()
    out = []
    for i, w in enumerate(words):
        lw = w.lower()
        core = re.sub(r"[^A-Za-z.]", "", w)
        if core.upper() in ACRONYMS or re.fullmatch(r"[IVX]{2,5}", core) or (
                core.isalpha() and len(core) >= 2 and not re.search(r"[AEIOUY]", core.upper())):
            out.append(w)  # keep acronyms (NAU, ABOR, COFS, HR, FMLA)
        elif i > 0 and lw in small:
            out.append(lw)
        else:
            out.append(w[:1].upper() + w[1:].lower())
    return " ".join(out)


CONNECTORS = {"and", "of", "or", "the", "for", "to", "in", "with", "on", "by", "a", "an"}
TEMPLATE_HEADINGS = {"policy", "definitions", "responsibilities", "procedures", "appendix", "appendix*", "sources",
                     "forms", "history", "purpose", "scope", "exceptions", "summary"}


def _continues_heading(prev: str, cur: str) -> bool:
    """True if `cur` looks like the second line of a heading that wrapped."""
    pw, cw = prev.split(), cur.split()
    if not pw or not cw or prev.endswith((":", "?", ".")):
        return False
    if cw[0].lower() in CONNECTORS or pw[-1].lower() in CONNECTORS:
        return True
    return len(cw) == 1 and cw[0].lower().strip(":") not in TEMPLATE_HEADINGS


def caps_heading_line(s: str) -> str:
    """Markdown heading for an ALL-CAPS line, or the line unchanged."""
    return "### " + _heading_text(s) if _is_caps_heading(s) and not LIST_START_RE.match(s) else s


def strip_running_lines(pages: list) -> list:
    """Remove header/footer lines that repeat across pages (digits ignored)."""
    if len(pages) < 2:
        return [re.sub(r"(?im)^.*\bpage\s+\d+\s+of\s+\d+\s*$", "", p) for p in pages]
    def key(line):
        # ignore digits and spacing (PDF text sometimes splits words: "Ac ademic")
        return re.sub(r"\d+", "#", re.sub(r"\s+", "", line.lower()))
    counts: dict = {}
    for p in pages:
        lines = [l for l in p.split("\n") if l.strip()]
        for l in set(key(x) for x in lines[:3] + lines[-3:]):
            counts[l] = counts.get(l, 0) + 1
    threshold = max(2, (len(pages) + 1) // 2)
    repeated = {k for k, n in counts.items() if n >= threshold and len(k) > 1}
    out = []
    for p in pages:
        kept = [l for l in p.split("\n") if key(l) not in repeated
                and not re.fullmatch(r"\s*(page\s+)?\d+(\s+of\s+\d+)?\s*", l, flags=re.I)
                and not re.search(r"/.*\bpage\s+\d+\s+of\s+\d+\s*$", l, flags=re.I)]
        out.append("\n".join(kept))
    return out


def reflow_pdf_text(text: str) -> str:
    """Turn raw PDF text into readable Markdown-ish text: rejoin wrapped lines,
    mark ALL-CAPS headings, normalise bullets, drop bare page numbers."""
    text = text.replace("\r", "").replace("­", "")
    raw_lines = [l.strip() for l in text.split("\n") if l.strip()]
    lengths = sorted(len(l) for l in raw_lines) or [80]
    wrap_width = lengths[int(len(lengths) * 0.9) - 1 if len(lengths) > 1 else 0]
    out_paras = []
    for para in re.split(r"\n\s*\n", text):
        merged: list = []
        for line in para.split("\n"):
            s = line.strip()
            if not s or re.fullmatch(r"(Page\s+)?\d+(\s+of\s+\d+)?", s, flags=re.I):
                continue
            s = BULLET_RE.sub("- ", s)
            s = re.sub(r"\s{2,}", " ", s)
            if _is_caps_heading(s) and not LIST_START_RE.match(s):
                h = _heading_text(s)
                prev_h = merged[-1][5:-1] if merged and merged[-1].startswith("\n### ") else None
                if prev_h and _continues_heading(prev_h, h):
                    tail = h[:1].lower() + h[1:] if h.split()[0].lower() in CONNECTORS else h
                    merged[-1] = "\n### " + prev_h + " " + tail + "\n"
                else:
                    merged.append("\n### " + h + "\n")
                continue
            if merged and not merged[-1].startswith("\n###"):
                prev = merged[-1]
                ends_sentence = re.search(r"[.:;!?\]\"”]$", prev)
                if prev.endswith("-") and s[:1].islower():
                    merged[-1] = prev[:-1] + s
                    continue
                if not ends_sentence and not LIST_START_RE.match(s) and (
                        s[:1].islower() or s[:1] in ",(&)" or len(prev) >= 0.8 * wrap_width):
                    merged[-1] = prev + " " + s
                    continue
            merged.append(s)
        if merged:
            out_paras.append("\n".join(merged))
    out = "\n\n".join(out_paras)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip() + "\n"
