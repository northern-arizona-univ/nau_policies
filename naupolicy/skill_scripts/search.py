#!/usr/bin/env python3
"""Rank NAU policies (and their supporting documents) for a question or keywords.

Usage (run from the skill folder):
  python3 scripts/search.py incomplete grade deadline
  python3 scripts/search.py "athletic excuse" --top 5
  python3 scripts/search.py bereavement --docs        # also rank supporting documents

Scoring: title words count most, then NAU's own subject-index terms (aliases.csv) and
keywords, then how often the words appear in the text. Exact phrases in quotes get a bonus.
Prints id, title, status, dates and the best-matching line for each hit.
"""
import csv
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent / "references"
POLICY_RE = re.compile(r"<!-- POLICY id=(\S+) -->\n(.*?)<!-- END POLICY -->", re.S)
DOC_RE = re.compile(r"<!-- DOCUMENT id=(\S+) owner=(\S*) -->\n(.*?)<!-- END DOCUMENT -->", re.S)
STOP = set("""a an and are as at be by can do does for from has have how i if in is it its me my
of on or our policy policies nau northern arizona university should that the their there this to
under was what when where which who why will with would you your about any must""".split())


def field(text, name):
    m = re.search(rf"^{name}: ?(.*)$", text, re.M)
    return m.group(1).strip().strip("'\"") if m else ""


def keywords(front):
    m = re.search(r"^keywords:\n((?:- .*\n?)+)", front, re.M)
    return " ".join(x[2:] for x in m.group(1).splitlines()) if m else ""


def load_aliases():
    out = {}
    p = HERE / "aliases.csv"
    if p.exists():
        with open(p, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                if row.get("target_id"):
                    out.setdefault(row["target_id"], []).append(row["term"].lower())
    return out


def stem(w):
    for suf in ("ings", "ing", "ies", "es", "s", "ed"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    top = 8
    with_docs = "--docs" in argv
    args = [a for a in argv if a != "--docs"]
    if "--top" in args:
        i = args.index("--top")
        top = int(args[i + 1])
        del args[i:i + 2]
    query = " ".join(args)
    phrases = [p.lower() for p in re.findall(r'"([^"]+)"', query)]
    terms = [stem(w) for w in re.findall(r"[a-z0-9]+", query.lower()) if w not in STOP and len(w) > 1]
    if not terms:
        print("Give some keywords.")
        return 1
    aliases = load_aliases()

    def score(title, kw, body, rid):
        t, b, k = title.lower(), body.lower(), kw.lower()
        al = " ".join(aliases.get(rid, []))
        s = 0.0
        for term in terms:
            pat = re.compile(r"\b" + re.escape(term))
            s += 6 * len(pat.findall(t)) + 4 * len(pat.findall(al)) + 3 * len(pat.findall(k))
            s += min(len(pat.findall(b)), 15) * 0.5
        s += sum(8 for p in phrases if p in t or p in al) + sum(4 for p in phrases if p in b)
        if all(re.search(r"\b" + re.escape(term), t + " " + al + " " + b) for term in terms):
            s *= 1.5
        return s

    def best_line(body):
        best, best_n = "", 0
        for line in body.splitlines():
            if line.lstrip().startswith(("#", ">", "[")):
                continue  # headings, notes and bare links say little
            l = line.lower()
            n = sum(1 for term in terms if re.search(r"\b" + re.escape(term), l))
            if n > best_n and len(line.strip()) > 20:
                best, best_n = line.strip(), n
        return (best[:220] + "…") if len(best) > 220 else best

    hits = []
    for f in sorted((HERE / "policies").glob("*.md")):
        for m in POLICY_RE.finditer(f.read_text(encoding="utf-8")):
            rid, text = m.group(1), m.group(2)
            end = text.find("\n---\n", 4)
            front, body = (text[:end], text[end + 5:]) if end != -1 else ("", text)
            s = score(field(front, "title"), keywords(front) + " " + field(front, "type"), body, rid)
            if s > 0:
                hits.append((s, "policy", rid, front, body))
    if with_docs and (HERE / "documents").exists():
        for f in sorted((HERE / "documents").glob("*.md")):
            for m in DOC_RE.finditer(f.read_text(encoding="utf-8")):
                did, owner, text = m.groups()
                end = text.find("\n---\n", 4)
                front, body = (text[:end], text[end + 5:]) if end != -1 else ("", text)
                s = score(field(front, "title"), "", body, "") * 0.8
                if s > 0:
                    hits.append((s, "document", f"{did} (supporting document of {owner})", front, body))
    hits.sort(key=lambda h: -h[0])
    if not hits:
        print("No matches. Try other words or synonyms.")
        return 0
    for s, kind, rid, front, body in hits[:top]:
        status = field(front, "status") or "-"
        if field(front, "under_review") == "true":
            status += ", under review"
        dates = ", ".join(x for x in (f"effective {field(front, 'effective_date')}" if field(front, 'effective_date') else "",
                                      f"revised {field(front, 'last_revised')}" if field(front, 'last_revised') else "") if x)
        print(f"{s:6.1f}  {rid}\n        {field(front, 'title')}  [{status}{'; ' + dates if dates else ''}]")
        line = best_line(body)
        if line:
            print(f"        … {line}")
    print("\nOpen one with: python3 scripts/show.py <id>   (add --docs for supporting documents)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
