"""Rebuild data/documents/ from files saved in archive/<label>/ (no network)."""
from __future__ import annotations

from pathlib import Path

from bs4 import BeautifulSoup

from .documents import extract_text
from .output import read_front, write_md
from .util import file_ext, file_stem, slugify, to_markdown


def rebuild_documents(root: Path, label: str) -> int:
    archive = root / "archive" / label
    if not archive.exists():
        print(f"No archive for {label}")
        return 1
    files = {p.name[:10]: p for p in (archive / "files").glob("*") if p.is_file()}
    written, missing = 0, []
    for md in sorted((root / "data" / "policies").rglob("*.md")):
        front = read_front(md)
        for doc in front.get("documents") or []:
            target = doc.get("text_file")
            if not target or not target.startswith("data/documents/"):
                continue
            out = root / target
            if out.exists():
                continue
            if doc.get("link_type") == "page":
                src = archive / "html" / "linked" / (slugify(doc["url"], 120) + ".html")
                if not src.exists():
                    missing.append(doc["url"])
                    continue
                text = to_markdown(BeautifulSoup(src.read_text(encoding="utf-8"), "html.parser"))
            else:
                src = files.get((doc.get("sha256") or "")[:10])
                if src is None:
                    missing.append(doc["url"])
                    continue
                ext = file_ext(doc.get("final_url") or doc["url"]) or ""
                text, _, _ = extract_text(src.read_bytes(), ext)
                if not text:
                    missing.append(doc["url"])
                    continue
            title = doc.get("title") or file_stem(doc["url"])
            dfront = {"title": title, "owner": front["id"], "role": doc.get("role"), "url": doc["url"],
                      "sha256": doc.get("sha256"), "bytes": doc.get("bytes"), "pages": doc.get("pages"),
                      "text_problem": doc.get("text_problem"), "snapshot": front.get("snapshot"),
                      "retrieved": front.get("retrieved")}
            note = (f"> Text extracted automatically from [{title}]({doc['url']}) on {front.get('retrieved')}. "
                    "Layout, tables and numbering may be imperfect; the original file is authoritative.\n\n")
            write_md(out, dfront, f"# {title}\n\n" + note + text)
            written += 1
    print(f"Rebuilt {written} document text files" + (f"; {len(missing)} could not be rebuilt:" if missing else "."))
    for u in missing:
        print("  ", u)
    return 0
