#!/usr/bin/env python3
"""Print one NAU policy from the combined reference files.

Usage (run from the skill folder):
  python3 scripts/show.py upl/syllabus-requirements          # metadata + full text
  python3 scripts/show.py acad/100601 --meta                 # metadata (front matter) only
  python3 scripts/show.py upl/conditions-of-faculty-service --docs   # also its supporting documents
  python3 scripts/show.py upl/travel-policies --children     # list a bundle's numbered items
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent / "references"
POLICY_RE = re.compile(r"<!-- POLICY id=(\S+) -->\n(.*?)<!-- END POLICY -->", re.S)
DOC_RE = re.compile(r"<!-- DOCUMENT id=(\S+) owner=(\S*) -->\n(.*?)<!-- END DOCUMENT -->", re.S)


def policies():
    for f in sorted((HERE / "policies").glob("*.md")):
        for m in POLICY_RE.finditer(f.read_text(encoding="utf-8")):
            yield m.group(1), m.group(2), f.name


def documents():
    d = HERE / "documents"
    if not d.exists():
        return
    for f in sorted(d.glob("*.md")):
        for m in DOC_RE.finditer(f.read_text(encoding="utf-8")):
            yield m.group(1), m.group(2), m.group(3)


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    pid = argv[0].strip().rstrip("/")
    if pid.endswith(".md"):
        pid = pid[:-3]
    flags = set(argv[1:])
    found = None
    ids = []
    for rid, text, fname in policies():
        ids.append(rid)
        if rid == pid:
            found = (text, fname)
    if found is None:
        close = [i for i in ids if pid.split("/")[-1] in i][:15]
        print(f"No policy with id {pid!r}." + (" Did you mean: " + ", ".join(close) if close else
              " Use scripts/search.py to find ids."))
        return 1
    text, fname = found
    if "--children" in flags:
        kids = [i for i in ids if i.startswith(pid + "/")]
        print(f"{len(kids)} items under {pid}:")
        for rid, t, _ in policies():
            if rid in kids:
                m = re.search(r"^title: (.*)$", t, re.M)
                print(f"  {rid}  {m.group(1).strip() if m else ''}")
        return 0
    if "--meta" in flags:
        end = text.find("\n---\n", 4)
        print(text[: end + 5] if text.startswith("---") and end != -1 else text[:3000])
    else:
        print(f"[{pid} — from references/policies/{fname}]\n")
        print(text)
    if "--docs" in flags:
        docs = [(did, body) for did, owner, body in documents() if owner == pid]
        if not docs:
            print("\n(No separate supporting documents for this policy.)")
        for did, body in docs:
            print(f"\n\n===== Supporting document: {did} =====\n")
            print(body)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
