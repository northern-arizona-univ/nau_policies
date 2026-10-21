"""Offline parser checks against saved page samples. Run: python3 -m tests.test_parsers"""
from pathlib import Path

from naupolicy import academic, library

FX = Path(__file__).parent / "fixtures"
BASE = "https://in.nau.edu/university-policy-library/"


def load(name):
    return (FX / name).read_text(encoding="utf-8")


def test_full_text_page():
    r = library.parse_landing(load("syllabus-requirements.html"), BASE + "syllabus-requirements/",
                              "syllabus-requirements", "2026-10-12")
    assert r["title"] == "Syllabus Requirements", r["title"]
    assert r["kind"] == "full_text"
    assert r["effective_date"] == "2016-01-25" and r["last_revised"] == "2022-08-22"
    assert r["responsible_executive"] == "Provost"
    assert r["responsible_office"] == "Office of Curriculum and Assessment"
    assert r["contact_email"] == "Kerry.Thompson@nau.edu"
    assert r["who_should_know"][1] == "All faculty and graduate teaching assistants"
    assert r["entities_affected"] == ["Office of the Provost", "All Academic Units"]
    assert r["printable_pdf"].endswith("Syllabus-Requirements-1-1.pdf")
    assert any("future" in f for f in r["flags"]), r["flags"]
    assert len(r["history"]) == 3
    roles = {d["url"].rsplit("/", 1)[-1]: (d["role"], d["location"]) for d in r["documents"]}
    assert roles["Syllabus-Requirements-1-1.pdf"][0] == "printable"
    assert roles["Syllabus-Policy-Statements_08042026.pdf"] == ("document", "body")
    assert "## Policy Statement" in r["body_md"] and "Responsible Executive" not in r["body_md"]
    assert "printable" not in r["body_md"].lower()
    assert "Course Review Forms" in [x["text"] for x in r["related"]][-1]


def test_summary_page():
    r = library.parse_landing(load("faculty-workload.html"), BASE + "faculty-workload/", "faculty-workload", "2026-10-12")
    assert r["kind"] == "summary"
    assert r["effective_date"] == "2023-04-24"
    assert r["keywords"] == ["Workload"]
    pol = [d for d in r["documents"] if d["role"] == "policy"]
    assert len(pol) == 1 and pol[0]["url"].endswith("Faculty-Workload-4-24-23.pdf")
    assert "Keywords" not in r["body_md"]


def test_summary_with_extra_document():
    r = library.parse_landing(load("conditions-of-faculty-service.html"), BASE + "conditions-of-faculty-service/",
                              "conditions-of-faculty-service", "2026-10-12")
    assert r["last_revised"] == "Not Applicable"
    assert not any("unparsed" in f for f in r["flags"])
    by = {d["url"].rsplit("/", 1)[-1]: d for d in r["documents"]}
    assert by["Conditions-of-Faculty-Service-POLICY.pdf"]["role"] == "policy"
    assert by["NAU-Conditions-of-Faculty-Service-DOCUMENT.pdf"]["role"] == "document"
    assert by["6-201-Conditions%20of%20Faculty%20Service.pdf"]["location"] == "sidebar"
    assert r["keywords"] == ["COFS", "Faculty"]


def test_bundle():
    r = library.parse_landing(load("comptroller-policies.html"), BASE + "comptroller-policies/",
                              "comptroller-policies", "2026-10-12", bundle=True)
    assert r["kind"] == "bundle"
    codes = [(c["code"], c["section"], c["subgroup"]) for c in r["children"]]
    assert codes[0] == ("001", "Section 000. Introduction", None), codes
    assert codes[2] == ("102-02", "Section 100. General", "102 Budget and Reports"), codes
    assert (r["children"][3]["code"], r["children"][3]["title"], r["children"][3]["link_type"]) == ("535", "Lodging", "file")
    assert r["children"][4]["link_type"] == "landing"


def test_academic_detail():
    r = academic.parse_detail(load("academic-100302.html"), "https://www9.nau.edu/policies/Client/Details/819")
    assert r["number"] == "100302" and r["title"] == "Administrative Drop"
    assert r["type"] == "Enrollment" and r["effective_date"] == "2019-07-29"
    assert r["appeal_eligible"] is True
    assert r["sections"] == ["Policy", "General Procedure"]
    assert r["who_should_know"] == ["All students", "All faculty, instructors, and academic officials"]
    assert "### Policy Statement" in r["body_md"]
    assert r["related"][0]["url"] == "https://www9.nau.edu/policies/Client/Details/2420"


def test_pdf_cleanup():
    from naupolicy.util import reflow_pdf_text, strip_running_lines
    pages = strip_running_lines(["Academic Affairs / X  Page 1 of 2\nWHO SHOULD KNOW THIS POLICY\n▪ All faculty",
                                 "Ac ademic Affairs / X  Page 2 of 2\nTITLE IX AND\nNAU REPORTING\nText that wraps\nonto a new line."])
    out = reflow_pdf_text("\n\n".join(pages))
    assert "Page 1 of 2" not in out
    assert "### Who Should Know This Policy" in out
    assert "- All faculty" in out
    assert "### Title IX and NAU Reporting" in out, out
    assert "Text that wraps onto a new line." in out


def test_hr_numbers():
    assert library._official_number("hr_4-051", "4.05(1) Leave") == "HR 4.05(1)"
    assert library._official_number("hr_4-16", "Parental Leave of Absence") == "HR 4.16"
    assert library._official_number("trv-540-x", "TRV 540 – Meal and Incidental") == "TRV 540"


if __name__ == "__main__":
    n = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            n += 1
            print("ok", name)
    print(f"{n} tests passed")
