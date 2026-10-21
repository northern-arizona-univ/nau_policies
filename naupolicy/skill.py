"""Package data/ as an uploadable Claude skill: skill/nau-policies/ and skill/nau-policies.zip.

Claude's skill uploader accepts at most 200 files, so the ~440 policy files and their
supporting documents are combined into one Markdown file per manual. Each policy keeps
its front matter and is wrapped in markers that scripts/show.py and scripts/search.py use:

    <!-- POLICY id=policy-library/syllabus-requirements -->
    ---
    (front matter)
    ---
    (text)
    <!-- END POLICY -->
"""
from __future__ import annotations

import csv
import json
import re
import shutil
from collections import Counter, defaultdict
from pathlib import Path

from .output import read_front
from .util import slugify

SKILL_NAME = "nau-policies"
MAX_FILES = 200  # Claude's upload limit, counting files in the zip
BUNDLE_GROUPS = {"comptroller-policies", "travel-policies", "contracting-purchasing-policies"}


def _group_for(rid: str, front: dict) -> str:
    if rid.startswith("academic-catalog/"):
        return "academic-catalog"
    parts = rid.split("/")
    if len(parts) >= 2 and parts[1] in BUNDLE_GROUPS:
        return parts[1]                      # bundle page and all its items together
    manuals = [m.get("manual") for m in front.get("manuals") or [] if m.get("manual")]
    return slugify(manuals[0]) if manuals else "other"


def _strip_front(text: str) -> str:
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            return text[:end + 5], text[end + 5:].lstrip("\n")
    return "", text


def build_skill(root: Path, out: Path) -> int:
    out = out if out.is_absolute() else root / out
    data = root / "data"
    catalog = json.loads((data / "catalog.json").read_text(encoding="utf-8"))
    if not catalog:
        print("data/catalog.json is empty; run a crawl first")
        return 1
    label = Counter(r["snapshot"] for r in catalog.values()).most_common(1)[0][0]
    src = Counter(r["source"] for r in catalog.values())
    counts = (f"{src.get('university-policy-library', 0)} University Policy Library records "
              f"and {src.get('academic-catalog', 0)} Academic Catalog policies")

    skill_dir = out / SKILL_NAME
    shutil.rmtree(skill_dir, ignore_errors=True)
    refs = skill_dir / "references"
    (refs / "policies").mkdir(parents=True)
    (refs / "documents").mkdir(parents=True)

    # ---- policies, combined by manual -------------------------------------------------
    groups: dict = defaultdict(list)
    group_of: dict = {}
    retrieved = ""
    for md in sorted((data / "policies").rglob("*.md")):
        text = md.read_text(encoding="utf-8")
        front_txt, body = _strip_front(text)
        front = read_front(md)
        rid = front.get("id")
        if not rid:
            continue
        retrieved = max(retrieved, str(front.get("retrieved") or ""))
        g = _group_for(rid, front)
        group_of[rid] = g
        groups[g].append((rid, front_txt, body))
    for g, items in groups.items():
        items.sort(key=lambda x: x[0])
        parts = [f"# NAU policies: {g} (snapshot {label})\n\n"
                 "Each policy is between `<!-- POLICY id=… -->` and `<!-- END POLICY -->`. "
                 "Use `python3 scripts/show.py <id>` to print one.\n"]
        for rid, front_txt, body in items:
            parts.append(f"\n<!-- POLICY id={rid} -->\n{front_txt}\n{body.rstrip()}\n<!-- END POLICY -->\n")
        (refs / "policies" / f"{g}.md").write_text("".join(parts), encoding="utf-8")

    # ---- supporting documents, combined by the owning policy's group -------------------
    doc_groups: dict = defaultdict(list)
    doc_dir = data / "documents"
    if doc_dir.exists():
        for md in sorted(doc_dir.rglob("*.md")):
            front_txt, body = _strip_front(md.read_text(encoding="utf-8"))
            front = read_front(md)
            owner = front.get("owner", "")
            did = md.relative_to(doc_dir).with_suffix("").as_posix()
            doc_groups[group_of.get(owner, "other")].append((did, owner, front_txt, body))
    for g, items in doc_groups.items():
        parts = [f"# Supporting documents: {g} (snapshot {label})\n\n"
                 "Each document is between `<!-- DOCUMENT id=… owner=… -->` and `<!-- END DOCUMENT -->`. "
                 "`python3 scripts/show.py <policy id> --docs` prints a policy with its documents.\n"]
        for did, owner, front_txt, body in items:
            parts.append(f"\n<!-- DOCUMENT id={did} owner={owner} -->\n{front_txt}\n{body.rstrip()}\n<!-- END DOCUMENT -->\n")
        (refs / "documents" / f"{g}.md").write_text("".join(parts), encoding="utf-8")

    # ---- index, aliases, catalog (with the new file locations) -------------------------
    shutil.copy2(data / "index.md", refs / "index.md")
    if (data / "aliases.csv").exists():
        shutil.copy2(data / "aliases.csv", refs / "aliases.csv")
    if (data / "catalog.csv").exists():
        with open(data / "catalog.csv", encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        fields = list(rows[0].keys()) if rows else []
        for r in rows:
            r["path"] = f"references/policies/{group_of.get(r['id'], 'other')}.md"
        with open(refs / "catalog.csv", "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
    if (data / "process").exists():
        proc = [p.read_text(encoding="utf-8") for p in sorted((data / "process").glob("*.md"))]
        (refs / "process.md").write_text("\n\n---\n\n".join(proc), encoding="utf-8")

    # ---- scripts and SKILL.md ----------------------------------------------------------
    scripts = skill_dir / "scripts"
    scripts.mkdir()
    for name in ("search.py", "show.py"):
        shutil.copy2(Path(__file__).parent / "skill_scripts" / name, scripts / name)
    files_list = "\n".join(f"  - `references/policies/{g}.md` ({len(groups[g])})" for g in sorted(groups))
    template = (Path(__file__).parent / "skill_template.md").read_text(encoding="utf-8")
    (skill_dir / "SKILL.md").write_text(
        template.replace("{SNAPSHOT}", label).replace("{RETRIEVED}", retrieved or "unknown date")
        .replace("{COUNTS}", counts).replace("{POLICY_FILES}", files_list), encoding="utf-8")

    # ---- zip -------------------------------------------------------------------------
    zip_path = Path(str(out / SKILL_NAME) + ".zip")
    if zip_path.exists():
        zip_path.unlink()
    shutil.make_archive(str(out / SKILL_NAME), "zip", root_dir=out, base_dir=SKILL_NAME)
    n_files = sum(1 for p in skill_dir.rglob("*") if p.is_file())
    size = zip_path.stat().st_size / 1e6
    print(f"Skill folder: {skill_dir}  ({n_files} files)")
    print(f"Upload this:  {zip_path}  ({size:.1f} MB), snapshot {label}")
    if n_files > MAX_FILES:
        print(f"WARNING: {n_files} files exceeds Claude's {MAX_FILES}-file upload limit")
        return 1
    return 0
