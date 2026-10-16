---
name: nau-policies
description: Look up and explain Northern Arizona University (NAU) policies from a dated snapshot of the University Policy Library and the Academic Catalog policies. Use when someone asks what NAU policy says or requires, e.g. syllabus requirements, final exams, grading, incompletes, grade appeals, academic integrity, student absences and institutional excuses, faculty workload, conditions of faculty service, leave, outside employment, travel reimbursement, research, IT or campus rules.
---

# NAU policy reference

This skill holds a snapshot of NAU's published policies, captured **{RETRIEVED}** (snapshot `{SNAPSHOT}`): {COUNTS}. Every record links to the official page. NAU's own University Policy Library is authoritative and its FAQ says the library version controls if copies conflict, so always give the official link and the snapshot date.

## Files

All paths are relative to this skill's folder; run the commands below from there.

- `scripts/search.py`: ranks policies for a question or keywords and prints id, title, status, dates and the best-matching line.
- `scripts/show.py <id>`: prints one policy (metadata + full text). Add `--docs` for its supporting documents, `--meta` for metadata only, `--children` to list a bundle's numbered items.
- `references/index.md`: one row per policy (id, title, number, status, effective date, last revised, who should know, keywords/type), grouped by manual. Large; `grep` it rather than reading it whole.
- `references/aliases.csv`: NAU's own "Policies by Subject" terms (e.g. "Firearms", "Finals week", "Title IX") mapped to policy ids. `status` shows dead links.
- `references/catalog.csv`: the same rows as the index plus `path`, `responsible_office`, `audience` and `flags`.
- `references/policies/<group>.md`: the policy text, one file per manual. Each policy sits between `<!-- POLICY id=… -->` and `<!-- END POLICY -->`, with YAML front matter (metadata) followed by the text:
{POLICY_FILES}
- `references/documents/<group>.md`: supporting documents linked from policies (procedures, FAQs, templates, the full Conditions of Faculty Service document, drafts), between `<!-- DOCUMENT id=… owner=<policy id> -->` markers.
- `references/process.md`: policies open for comment and recently changed, as of the snapshot.

Policy ids look like:
- `upl/<slug>`: University Policy Library page (administrative, employment, campus, research, IT policies)
- `upl/<bundle>/<item>`: numbered items of the Comptroller, Travel and Contracting & Purchasing manuals
- `acad/<number>`: Academic Catalog policy (academic standards for students: grading, enrollment, appeals, integrity, degree requirements)

## How to answer

1. **Find candidates.** Search before reading:
   ```bash
   python3 scripts/search.py incomplete grade deadline
   python3 scripts/search.py "athletic excuse" --docs
   grep -i "incomplete" references/index.md references/aliases.csv
   ```
   Try synonyms (absence / attendance / excuse; cheating / plagiarism / integrity; leave / FMLA / sick). The quick map below covers common faculty questions.
2. **Pick the right source.** Academic standards that govern students (grades, incompletes, withdrawals, attendance requirements, integrity, appeals, degree requirements) live in `acad/`. Faculty employment and administrative rules live in `upl/`. Several topics exist in both (syllabus, institutional excuses, class meeting times, course numbering); read both and mention it if they differ.
3. **Read the policy.** Run `python3 scripts/show.py <id>` and read the front matter, then the relevant part of the text. Never answer from a search line or index row alone. For `kind: summary` records, the full policy text is under the heading "Policy document: …" or "Policy text from linked page: …" (extracted from the PDF or linked web page). For long policies you can pipe through `grep -n -i <word>` or `sed -n` to find the right section.
4. **Answer.** Lead with the direct answer. Support it with a short quotation or close paraphrase, naming the section (e.g. "Policy §A.3"). End with a source line:
   > Source: *Student Institutional Excuses* (Academic and Faculty Affairs), effective 2008-03-28, last revised 2025-08-01. Official page: <url>. From the NAU policy snapshot of {RETRIEVED}.
   Name the responsible office or contact from the front matter when the person needs to ask someone.
5. **Check whether it applies.** Use `who_should_know`, `entities_affected` and, for `acad/` policies, `audience` (graduate / undergraduate / personalized_learning). Many HR policies (`upl/hr_*`) are written for staff; faculty conditions are in Conditions of Faculty Service, which implements ABOR Policy 6-201.

## Always flag these

Read the front matter for each policy you rely on:

- `status: interim`: say it is an interim policy.
- `status: superseded`: say so and use the policy named in `superseded_by` instead.
- `under_review: true`, a `draft` document, or a flag mentioning a draft: a revision is in progress. Answer from the current policy. Mention the draft only if asked, and never present draft text as current.
- A flag `effective_date differs` or `last_revised differs`: the web page and the policy document disagree. Give both dates. The document is usually the newer one.
- `text_source` mentions a policy document: the text was extracted from a PDF. Quote carefully, and point to the original file for tables, forms or exact wording.
- No full text (`kind: stub`, a flag saying text was not captured, or policy text on an external site such as the ABOR manual): say the text is not in the snapshot and give the link.
- Time-sensitive questions (deadlines, amounts, current rates): note the snapshot date and suggest confirming on the official page.

## Limits

- Don't invent or extrapolate policy. If nothing relevant turns up, say so and suggest the University Policy Library (https://in.nau.edu/university-policy-library/) or policy@nau.edu.
- Not included: college or department policies (unit workload documents, bylaws, promotion and tenure criteria), Faculty Senate documents, and the full ABOR Policy Manual (https://www.azregents.edu/policy-manual). Say when a question depends on one of these.
- Explaining policy is not legal advice. For disputes, grievances or personnel actions, point to the responsible office named in the policy.

## Quick map for common faculty questions

| Topic | Start with |
|---|---|
| Syllabus content, required statements, AI or other syllabus language | `upl/syllabus-requirements` (use `--docs` for the policy statements, FAQ and template), `acad/100227` |
| Student absences, excused absences, athletics, military, bereavement | `upl/student-institutional-excuses`, `acad/100226`, `upl/attendance-accommodation`, `acad/100335` (graduate attendance) |
| Final exams, finals week, exam-week closure | `acad/100410`, `upl/administering-final-exams`, `acad/100210` |
| Grades, grading scale, GPA, grade submission | `acad/100412`, `acad/100401`, `upl/grade-submission`, `acad/100402` (mid-term) |
| Incompletes / in-progress grades | `acad/100404` (undergraduate), `acad/100406` (graduate) |
| Grade appeals and petitions | `acad/100105`, `acad/100104`, `acad/100106`, `acad/100103` |
| Academic integrity, cheating, plagiarism | `acad/100601` |
| Dropping a student who doesn't attend | `acad/100302`, `upl/administratively-dropping-student` |
| Class meeting times, credit hours | `upl/standard-class-meeting-times`, `acad/100311`, `acad/100814`, `upl/academic-credit` |
| Curriculum protocols, co-convening, cross-listing | `acad/200352`–`acad/200359`, `upl/curriculum-design-and-assessment` |
| Faculty workload, statements of expectation | `upl/faculty-workload` |
| Faculty appointments, review, promotion, tenure, sabbatical | `upl/conditions-of-faculty-service` with `--docs` (the full CoFS document) |
| Faculty ethics and conduct | `upl/faculty-code-of-ethics-and-conduct` |
| Supplemental pay, outside employment | `upl/supplemental-pay-for-faculty`, `upl/hr_1-09` |
| Consensual relationships, discrimination, harassment, Title IX | `upl/consensual-relationships`, `upl/nondiscrimination-anti-harassment`, `upl/sexual-misconduct` |
| Student records, FERPA | `upl/inspection-review-amendment-of-student-records` |
| Leave (parental, sick, FMLA) | `upl/hr_4-16`, `upl/hr_4-03`, `upl/hr_4-05` |
| Travel, meals and incidentals | `upl/travel-policies` (`--children` lists the items), `upl/trv-540-meals-and-incidental-expenses` |
| Research misconduct, PI eligibility, sponsored projects | `upl/misconduct-in-research`, `upl/principal-investigator-eligibility`, then the "Research" section of `index.md` |
| Email, IT use, data handling | `upl/electronic-mail`, `upl/appropriate-use-of-information-technology-resources`, `upl/data-classification-and-handling` |
