# NAU policies: versioned snapshots

A version-controlled copy of Northern Arizona University's published policies, kept as plain Markdown so it can be searched, compared between snapshots, and loaded by a Claude skill. NAU's own sites remain the authoritative versions; every record links back to them.

## Sources

| Source | What it holds | How text is captured |
|---|---|---|
| [University Policy Library](https://in.nau.edu/university-policy-library/) | ~185 administrative policies in 11 manuals | Policy pages; for pages that only summarize, the linked "View the Policy" PDF |
| [Academic Catalog policies](https://www9.nau.edu/policies/Client/IndexPaged?whoIsLooking=1) | ~92 academic policies (integrity, grading, enrollment, appeals) | Policy pages (full text is on the page) |
| [Policies by Subject](https://in.nau.edu/university-policy-library/by-subject/) | ~200 search terms pointing at policies | Saved as `data/aliases.csv` (synonyms for finding policies) |

ABOR policies, Faculty Senate documents and other external links found on manual pages are recorded in `data/external_links.csv` but not copied.

## Layout

```
sources.yaml                 what to crawl (edit this when NAU adds a manual)
npl/                         the crawler
data/
  policies/upl/<slug>.md     one file per Policy Library page (front matter + text)
  policies/upl/<bundle>/…    Comptroller, Travel, Contracting: one file per numbered item
  policies/acad/<number>.md  one file per Academic Catalog policy
  documents/<id>/…           text of supporting documents (procedures, FAQs, CoFS document…)
  catalog.csv / catalog.json one row per policy: dates, owner, status, path, content hash
  index.md                   compact table the skill reads first
  aliases.csv                By-Subject terms → policy ids (with dead-link status)
  external_links.csv         non-policy links found on manual pages
  process/                   "Open for comment" and "Recent changes" pages as captured
  runs/<label>.md            what each run found: counts, flags, dead links, extraction problems
CHANGELOG.md                 added / removed / revised / quietly changed, per snapshot
archive/<label>/             original HTML and PDF/Word files (not committed to Git)
```

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
python3 -m npl crawl --label 2027-spring      # full run, ~15–20 minutes
git add -A && git commit -m "Snapshot 2027-spring"
git tag snapshot-2027-spring
```

Then read `data/runs/2027-spring.md` and the new section at the top of `CHANGELOG.md`.

Useful options: `--pilot` (Academic & Faculty Affairs + Academic Catalog only), `--manual human-resources` (one manual; repeatable), `--no-academic`, `--no-library`, `--no-documents`, `--academic-limit 10`, `--delay 2`.

Partial runs update only what they touched and never mark anything as removed; only a full run detects removals.

## Versioning

* **Official version**: `effective_date`, `last_revised` and `history` as published.
* **Observed version**: `content_sha256` (page + extracted policy text) and a sha256 for every downloaded document. A changed hash without a new revision date shows up in the changelog as "text changed without a new revision date".
* Git history holds every snapshot; tags mark them. `git diff snapshot-2026-fall snapshot-2027-spring -- data/policies` shows wording changes.

## Tests

```bash
python3 -m tests.test_parsers
```

Parser checks against saved samples of each page layout (`tests/fixtures/`).
