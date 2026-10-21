# NAU policies: versioned snapshots

A version-controlled copy of Northern Arizona University's published policies, kept as plain Markdown so it can be searched, compared between snapshots, and loaded by a Claude skill. NAU's own sites remain the authoritative versions; every record links back to them.

## Sources

| Source | What it holds | How text is captured |
|---|---|---|
| [University Policy Library](https://in.nau.edu/university-policy-library/) | ~185 administrative policies in 11 manuals | Policy pages; for pages that only summarize, the linked "View the Policy" PDF |
| [Academic Catalog policies](https://www9.nau.edu/policies/Client/IndexPaged?whoIsLooking=1) | ~92 academic policies (integrity, grading, enrollment, appeals) | Policy pages (full text is on the page) |
| [Policies by Subject](https://in.nau.edu/university-policy-library/by-subject/) | ~200 search terms pointing at policies | Saved as `data/aliases.csv` (synonyms for finding policies) |

ABOR policies, Faculty Senate documents and other external links found on manual pages are recorded in `data/external_links.csv` but not copied.

## Understanding the repository

```
nau_policies/
├── sources.yaml          what to crawl: URLs, the 11 manuals, which pages are bundles
├── naupolicy/            the tool that builds everything below (crawler, parsers, skill builder)
├── tests/                checks that the parsers still read NAU's page layouts correctly
├── data/                 the snapshot itself (committed to Git)
│   ├── policies/
│   │   ├── policy-library/      University Policy Library: one file per policy page
│   │   │   └── <bundle>/        Comptroller, Travel, Contracting: one file per numbered item
│   │   └── academic-catalog/    Academic Catalog policies: one file per numbered policy
│   ├── documents/        supporting files linked from a policy (procedures, FAQs, CoFS document, drafts)
│   ├── process/          NAU's "Policies Open for Comment" and "Recent Policy Changes" pages
│   ├── runs/             one quality report per crawl
│   ├── catalog.csv       one row per policy: id, title, dates, status, owner, flags (open in Excel)
│   ├── catalog.json      the same, used to compare against the previous snapshot
│   ├── index.md          compact table the skill searches first
│   ├── aliases.csv       NAU's "Policies by Subject" terms → policy ids, with dead links marked
│   └── external_links.csv non-policy links on manual pages (ABOR, Faculty Senate…)
├── CHANGELOG.md          what changed between snapshots
├── archive/              original HTML and PDF/Word files per snapshot (local only, not in Git)
└── skill/                the built Claude skill and zip (local only, rebuilt from data/)
```

### Why policies are split into `policy-library` and `academic-catalog`

NAU publishes policies in two unrelated systems, and each identifies policies differently:

- **`policy-library/`**: the [University Policy Library](https://in.nau.edu/university-policy-library/) on in.nau.edu (administrative, employment, campus, research and IT policies). Policies are identified by their web address, so `policy-library/syllabus-requirements.md` comes from `…/university-policy-library/syllabus-requirements/`. The Comptroller, Travel and Contracting manuals are single pages listing many numbered documents, so each gets a subfolder with one file per item, e.g. `policy-library/travel-policies/545-01.md`.
- **`academic-catalog/`**: the [Academic Catalog policy system](https://www9.nau.edu/policies/Client/IndexPaged?whoIsLooking=1) on www9.nau.edu (academic standards for students: grading, incompletes, appeals, integrity, degree requirements). Policies have 6-digit numbers, so Academic Integrity is `academic-catalog/100601.md`.

A policy's **id** is its path without `.md` (e.g. `policy-library/faculty-workload`, `academic-catalog/100404`). Ids appear in `catalog.csv`, `aliases.csv`, the changelog and the skill.

### Why supporting documents are separate

Each policy file holds the policy itself. When a page only summarizes a policy and links the full text as a "View the Policy" PDF, that PDF's text is copied into the policy file. Pages also link other material: procedures, FAQs, forms, templates, drafts, and documents such as the 72-page Conditions of Faculty Service document. These live in `documents/<policy id>/` because they are not the policy and NAU revises them on their own schedule (the syllabus policy statements changed in 2026 while the policy did not). Keeping them apart lets the changelog report "document changed" separately from "policy revised", and keeps a draft from ever being read as the current policy.

### `process/` and `runs/`

- **`process/`** is context, not policy: copies of NAU's "Policies Open for Comment" and "Recent Policy Changes" pages as they were on crawl day, so the skill can say a policy is being revised.
- **`runs/<label>.md`** is the quality report for each crawl: record counts, flagged problems (web page and PDF dates disagree, text not captured, scanned PDFs), dead links and broken files. Read it after every crawl.

### The `naupolicy` tool

| File | Job |
|---|---|
| `__main__.py` | The commands: `crawl`, `skill`, `rebuild-documents` (`python3 -m naupolicy …`) |
| `crawl.py` | Runs a snapshot: fetches pages, writes `data/`, the changelog and the run report |
| `library.py` | Reads Policy Library pages: metadata, sections, linked files, bundles, drafts |
| `academic.py` | Reads Academic Catalog pages |
| `documents.py` | Extracts text from PDFs and Word files |
| `fetch.py` | Polite downloading (one request a second, retries) |
| `util.py` | Shared helpers: dates, HTML → Markdown, PDF text cleanup |
| `output.py` | Writes the Markdown files, catalog, index and changelog |
| `rebuild.py` | Regenerates `data/documents/` from `archive/` without going online |
| `skill.py`, `skill_template.md`, `skill_scripts/` | Build the uploadable Claude skill |

### Record fields (front matter)

`id`, `title`, `source`, `kind` (`full_text`, `summary`, `bundle`, `bundle_item`, `document_only`), `status` (`active`/`interim`), `under_review`, `official_number`, `manuals` (with group), `responsible_executive`, `responsible_office`, `contact`, `effective_date`, `last_revised`, `history`, `who_should_know`, `entities_affected`, `keywords`, `sections`, `text_source`, `url`, `documents` (url, role, sha256, text file), `related`, `content_sha256`, `snapshot`, `retrieved`, `flags`. Academic Catalog records add `type`, `audience`, `appeal_eligible`, `petition_eligible`, `fees_may_apply`, `internal_version_id`, `future_versions`.

Dates are stored exactly as NAU publishes them (ISO format when parseable). Inconsistencies are listed in `flags` rather than corrected.

## Running a snapshot

Run from Terminal on your Mac (the NAU sites are reachable there). One-time setup:

```bash
cd ~/Developer/nau_policies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
git init            # first time only
```

Each snapshot (e.g. August and January):

```bash
source .venv/bin/activate
python3 -m naupolicy crawl --label 2027-spring      # full run, ~15–20 minutes
git add -A && git commit -m "Snapshot 2027-spring"
git tag snapshot-2027-spring
```

Then read `data/runs/2027-spring.md` and the new section at the top of `CHANGELOG.md`.

Useful options: `--pilot` (Academic & Faculty Affairs + Academic Catalog only), `--manual human-resources` (one manual; repeatable), `--no-academic`, `--no-library`, `--no-documents`, `--academic-limit 10`, `--delay 2`.

Partial runs update only what they touched and never mark anything as removed; only a full run detects removals.

## The Claude skill

The skill (`nau-policies`) packages the current snapshot so Claude can answer policy questions from it: it ranks policies with `scripts/search.py`, prints the matching ones with `scripts/show.py`, and answers with the policy title, section, dates, official link and snapshot date. Its instructions live in `naupolicy/skill_template.md` and its two scripts in `naupolicy/skill_scripts/` (standard-library Python only); the snapshot label, capture date and record counts are filled in when you build it.

Claude's skill uploader accepts at most **200 files**, so the package does not mirror `data/` file-for-file: policies are combined into one Markdown file per manual (`references/policies/<manual>.md`) and supporting documents likewise (`references/documents/<manual>.md`), each policy wrapped in `<!-- POLICY id=… -->` markers that the scripts read. The whole skill is about 32 files. `data/` itself stays one file per policy so Git diffs between snapshots remain readable. The build stops with a warning if the package ever exceeds 200 files.

### Build

```bash
cd ~/Developer/nau_policies
source .venv/bin/activate
python3 -m naupolicy skill
```

This writes `skill/nau-policies/` (`SKILL.md`, `scripts/`, and `references/` with the index, aliases, catalog, combined policy and document files, and process pages) and `skill/nau-policies.zip`, and prints the file count, zip size and snapshot label. `skill/` is in `.gitignore` because it is generated from `data/`. Rebuild it whenever `data/` changes.

Optional check that the zip has the layout Claude expects (every entry starts with `nau-policies/`):

```bash
unzip -l skill/nau-policies.zip | head
```

### Install

Skills only work when code execution is turned on, because Claude reads the skill's files in its code-execution sandbox. Skills are available on Free, Pro, Max, Team and Enterprise plans.

**1. Turn on code execution**

- *Individual accounts (Free, Pro, Max):* in Claude (web or desktop) go to **Settings → Capabilities** and turn on **Code execution and file creation**.
- *Team and Enterprise:* an organization owner must first allow it under **Organization settings → Plugins & skills → Policy**, where both **Code execution and file creation** (shown as *Cloud code execution and file creation* in some versions) and **Skills** must be on. On Team plans these are on by default. Each member then checks **Settings → Capabilities** as above. If the option to upload skills is missing, the owner has turned off member-created skills.

**2. Upload the skill**

1. Go to **Customize → Skills**.
2. Click **+**, then **+ Create skill**, then **Upload a skill**.
3. Choose `skill/nau-policies.zip`.
4. Find **nau-policies** in the list and switch its toggle on. An uploaded skill is private to you until you share it.

**3. Test it**

Start a new chat and ask something the skill should handle, e.g. *"Under NAU policy, how long does an undergraduate have to finish an Incomplete?"* or *"Do I have to honor an athletic excuse a student gives me two days before the trip?"* The answer should name the policy, cite the section, give the official link and mention the snapshot date. If Claude answers without using the skill, check that code execution is on and the skill's toggle is enabled.

**4. Share with colleagues (Team/Enterprise)**

Open the skill under **Customize → Skills** and use **Share** (specific people) or **Publish to org** (everyone in the organization). Colleagues still need code execution turned on in their own **Settings → Capabilities**.

For Claude Code, copy the folder instead: `cp -r skill/nau-policies ~/.claude/skills/`.

### Update after a new snapshot

```bash
python3 -m naupolicy crawl --label 2027-spring
git add -A && git commit -m "Snapshot 2027-spring" && git tag snapshot-2027-spring
python3 -m naupolicy skill
```

Then upload the new `skill/nau-policies.zip` in **Customize → Skills**, replacing the previous version, so everyone using it gets the new data. To change how the skill behaves (wording, the quick-reference table of common faculty questions), edit `naupolicy/skill_template.md` and rebuild.

### Rebuilding document text offline

`python3 -m naupolicy rebuild-documents --label <label>` re-creates any missing files in `data/documents/` from `archive/<label>/` without going online (useful after improving text extraction).

## Versioning

* **Official version**: `effective_date`, `last_revised` and `history` as published.
* **Observed version**: `content_sha256` (page + extracted policy text) and a sha256 for every downloaded document. A changed hash without a new revision date shows up in the changelog as "text changed without a new revision date".
* Git history holds every snapshot; tags mark them. `git diff snapshot-2026-fall snapshot-2027-spring -- data/policies` shows wording changes.

## Tests

```bash
python3 -m tests.test_parsers
```

Parser checks against saved samples of each page layout (`tests/fixtures/`).
