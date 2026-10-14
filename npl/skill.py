"""Package data/ as an uploadable Claude skill: skill/nau-policies/ and skill/nau-policies.zip."""
from __future__ import annotations

import json
import shutil
from collections import Counter
from pathlib import Path

SKILL_NAME = "nau-policies"


def build_skill(root: Path, out: Path) -> int:
    out = out if out.is_absolute() else root / out
    data = root / "data"
    catalog = json.loads((data / "catalog.json").read_text(encoding="utf-8"))
    if not catalog:
        print("data/catalog.json is empty; run a crawl first")
        return 1
    label = Counter(r["snapshot"] for r in catalog.values()).most_common(1)[0][0]
    retrieved = _latest_retrieved(data)
    src = Counter(r["source"] for r in catalog.values())
    counts = (f"{src.get('university-policy-library', 0)} University Policy Library records "
              f"and {src.get('academic-catalog', 0)} Academic Catalog policies")

    skill_dir = out / SKILL_NAME
    shutil.rmtree(skill_dir, ignore_errors=True)
    refs = skill_dir / "references"
    refs.mkdir(parents=True)
    template = (Path(__file__).parent / "skill_template.md").read_text(encoding="utf-8")
    (skill_dir / "SKILL.md").write_text(
        template.replace("{SNAPSHOT}", label).replace("{RETRIEVED}", retrieved).replace("{COUNTS}", counts),
        encoding="utf-8")
    for name in ("index.md", "aliases.csv", "catalog.csv"):
        if (data / name).exists():
            shutil.copy2(data / name, refs / name)
    for sub in ("policies", "documents", "process"):
        if (data / sub).exists():
            shutil.copytree(data / sub, refs / sub)

    zip_base = out / SKILL_NAME
    if Path(str(zip_base) + ".zip").exists():
        Path(str(zip_base) + ".zip").unlink()
    archive = shutil.make_archive(str(zip_base), "zip", root_dir=out, base_dir=SKILL_NAME)
    n_files = sum(1 for p in skill_dir.rglob("*") if p.is_file())
    size = Path(archive).stat().st_size / 1e6
    print(f"Skill folder: {skill_dir}  ({n_files} files)")
    print(f"Upload this:  {archive}  ({size:.1f} MB), snapshot {label}")
    return 0


def _latest_retrieved(data: Path) -> str:
    import re
    best = ""
    for p in (data / "policies").rglob("*.md"):
        with open(p, encoding="utf-8") as f:
            for line in f:
                if line.startswith("retrieved:"):
                    best = max(best, re.sub(r"[^0-9-]", "", line.split(":", 1)[1]))
                    break
                if line.strip() == "---" and best:
                    pass
    return best or "unknown date"
