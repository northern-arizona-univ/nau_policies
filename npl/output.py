"""Writing records, the catalog, the skill index, the changelog and run reports."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Dict, List

import yaml


class _Dumper(yaml.SafeDumper):
    pass


def _str_presenter(dumper, data):
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


_Dumper.add_representer(str, _str_presenter)


def dump_yaml(obj) -> str:
    return yaml.dump(obj, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=1000, default_flow_style=False)


def clean(d):
    """Drop empty values so front matter stays readable."""
    if isinstance(d, dict):
        return {k: clean(v) for k, v in d.items() if v not in (None, "", [], {}) and not str(k).startswith("_")}
    if isinstance(d, list):
        return [clean(x) for x in d]
    return d


def write_md(path: Path, front: dict, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("---\n" + dump_yaml(clean(front)) + "---\n\n" + body.rstrip() + "\n", encoding="utf-8")


def read_front(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    return yaml.safe_load(text[4:end]) or {}


CSV_FIELDS = ["id", "source", "title", "official_number", "kind", "status", "manuals", "group",
              "effective_date", "last_revised", "type", "audience", "who_should_know", "keywords",
              "responsible_office", "under_review", "url", "path", "text_source", "flags", "snapshot"]


def write_catalog(root: Path, catalog: Dict[str, dict]) -> None:
    data = root / "data"
    data.mkdir(parents=True, exist_ok=True)
    (data / "catalog.json").write_text(json.dumps(catalog, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    with open(data / "catalog.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        w.writeheader()
        for rid in sorted(catalog):
            row = dict(catalog[rid])
            for k in ("manuals", "who_should_know", "keywords", "audience", "flags"):
                if isinstance(row.get(k), list):
                    row[k] = "; ".join(str(x) for x in row[k])
            w.writerow(row)


def write_csv(path: Path, rows: List[dict], fields: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _short(items, n=110) -> str:
    s = "; ".join(items or [])
    return s if len(s) <= n else s[: n - 1] + "…"


def _cell(s) -> str:
    return str(s or "").replace("|", "/").replace("\n", " ")


def write_index(root: Path, catalog: Dict[str, dict], label: str) -> None:
    """Compact Markdown index the skill reads first."""
    lines = [f"# NAU policy index (snapshot {label})", "",
             "One row per policy. Open the file in `path` for full text. "
             "Dates are as published by NAU; `under_review` means a revision is open for comment.", ""]
    groups: Dict[str, List[dict]] = {}
    for r in catalog.values():
        if r.get("kind") == "bundle_item":
            key = "Bundles: " + (r.get("group") or "")
        elif r["source"] == "academic-catalog":
            key = "Academic Catalog policies (academic standards, grading, enrollment, appeals)"
        else:
            key = "University Policy Library: " + ((r.get("manuals") or ["(not in a manual)"])[0])
        groups.setdefault(key, []).append(r)
    for key in sorted(groups, key=lambda k: (not k.startswith("Academic"), k)):
        lines += [f"## {key}", "",
                  "| id | title | no. | status | effective | revised | who should know | keywords / type |",
                  "|---|---|---|---|---|---|---|---|"]
        for r in sorted(groups[key], key=lambda r: (r.get("official_number") or "", r["title"])):
            status = r.get("status", "")
            if r.get("under_review"):
                status += ", under review"
            kw = r.get("type") or _short(r.get("keywords"), 60)
            lines.append("| " + " | ".join(_cell(x) for x in [
                r["id"], r["title"], r.get("official_number"), status, r.get("effective_date"),
                r.get("last_revised"), _short(r.get("who_should_know")), kw]) + " |")
        lines.append("")
    (root / "data" / "index.md").write_text("\n".join(lines), encoding="utf-8")


def changelog_entry(prev: Dict[str, dict], cur: Dict[str, dict], label: str, run_date: str,
                    full_scope: bool, scope_desc: str) -> str:
    out = [f"## {label} (run {run_date})", "", f"Scope: {scope_desc}", ""]
    if not prev:
        out += [f"Initial snapshot: {len(cur)} records.", ""]
        return "\n".join(out)
    added = sorted(set(cur) - set(prev))
    removed = sorted(set(prev) - set(cur)) if full_scope else []
    revised, text_only, status, docs = [], [], [], []
    for rid in sorted(set(cur) & set(prev)):
        a, b = prev[rid], cur[rid]
        if b.get("snapshot") != label:
            continue  # carried over, not re-checked this run
        da = (a.get("last_revised"), a.get("effective_date"))
        db = (b.get("last_revised"), b.get("effective_date"))
        if da != db:
            revised.append(f"- **{b['title']}** (`{rid}`): effective {da[1]} → {db[1]}, revised {da[0]} → {db[0]}")
        elif a.get("content_sha256") != b.get("content_sha256"):
            text_only.append(f"- **{b['title']}** (`{rid}`): text changed with no new revision date")
        if a.get("status") != b.get("status") or bool(a.get("under_review")) != bool(b.get("under_review")):
            status.append(f"- **{b['title']}** (`{rid}`): {a.get('status')}{' (under review)' if a.get('under_review') else ''}"
                          f" → {b.get('status')}{' (under review)' if b.get('under_review') else ''}")
        ha, hb = a.get("doc_hashes") or {}, b.get("doc_hashes") or {}
        for u in sorted(set(ha) | set(hb)):
            if u not in ha:
                docs.append(f"- `{rid}`: new document {u}")
            elif u not in hb:
                docs.append(f"- `{rid}`: document no longer linked {u}")
            elif ha[u] != hb[u]:
                docs.append(f"- `{rid}`: document content changed {u}")
    def sect(title, items):
        if items:
            out.extend([f"### {title}", ""] + items + [""])
    sect("Added", [f"- **{cur[r]['title']}** (`{r}`)" for r in added])
    sect("Removed", [f"- **{prev[r]['title']}** (`{r}`)" for r in removed])
    sect("Officially revised (dates changed)", revised)
    sect("Text changed without a new revision date", text_only)
    sect("Status changes", status)
    sect("Attached documents", docs)
    if len(out) == 4:
        out += ["No changes detected.", ""]
    return "\n".join(out)


def prepend_changelog(root: Path, entry: str) -> None:
    path = root / "CHANGELOG.md"
    head = "# Changelog\n\nGenerated by `python3 -m npl crawl`. Newest first.\n\n"
    old = path.read_text(encoding="utf-8") if path.exists() else head
    body = old[len(head):] if old.startswith(head) else old
    path.write_text(head + entry.rstrip() + "\n\n" + body.lstrip(), encoding="utf-8")
