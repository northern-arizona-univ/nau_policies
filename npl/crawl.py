"""Crawl NAU policy sources and write a snapshot into data/."""
from __future__ import annotations

import datetime as _dt
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

import yaml

from . import academic, library
from .documents import extract_text
from .fetch import Fetcher
from .output import (changelog_entry, prepend_changelog, write_catalog, write_csv,
                     write_index, write_md)
from .util import file_ext, file_stem, norm, sha256, slugify


def log(msg: str) -> None:
    print(msg, flush=True)


class Ctx:
    def __init__(self, root: Path, cfg: dict, label: str, args):
        self.root = root
        self.cfg = cfg
        self.label = label
        self.args = args
        self.today = _dt.date.today().isoformat()
        self.fetch = Fetcher(cfg["user_agent"], delay=args.delay if args.delay is not None else cfg.get("delay_seconds", 1.0),
                             timeout=cfg.get("timeout_seconds", 45))
        self.archive = root / "archive" / label
        self.data = root / "data"
        self.records: Dict[str, dict] = {}      # id -> record (front + body)
        self.doc_text_paths: Dict[str, str] = {}  # sha -> relative path of written text
        self.report = {"dead_pages": [], "broken_documents": [], "text_problems": [], "warnings": [],
                       "external_links": [], "skipped_documents": []}

    def save_raw(self, kind: str, name: str, content) -> None:
        p = self.archive / kind / name
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, str):
            p.write_text(content, encoding="utf-8")
        else:
            p.write_bytes(content)

    def rel(self, p: Path) -> str:
        return p.relative_to(self.root).as_posix()


# --------------------------------------------------------------------------- documents

def process_document(ctx: Ctx, owner_id: str, doc: dict) -> Optional[str]:
    """Download + extract one linked file. Returns extracted text (or None)."""
    dcfg = ctx.cfg["documents"]
    url = doc["url"]
    host = urlparse(url).netloc.lower()
    if not any(host == d or host.endswith("." + d) for d in dcfg["download_domains"]):
        doc["downloaded"] = False
        doc["note"] = "external host: link only"
        return None
    if any(re.search(p, url) for p in dcfg.get("skip_url_patterns", [])):
        doc["downloaded"] = False
        doc["note"] = "skipped by sources.yaml"
        return None
    if ctx.args.no_documents or not dcfg.get("extract_text", True):
        doc["downloaded"] = False
        return None
    r = ctx.fetch.get(url, max_bytes=int(dcfg.get("max_megabytes", 25) * 1024 * 1024))
    if not r.ok or not r.content:
        doc["downloaded"] = False
        doc["http_status"] = r.status
        if r.error:
            doc["error"] = r.error
        ctx.report["broken_documents"].append({"owner": owner_id, "url": url, "status": r.status, "error": r.error})
        return None
    doc["downloaded"] = True
    doc["sha256"] = sha256(r.content)
    doc["bytes"] = len(r.content)
    if r.final_url != url:
        doc["final_url"] = r.final_url
    ext = file_ext(r.final_url) or file_ext(url) or ""
    name = urlparse(url).path.rsplit("/", 1)[-1]
    ctx.save_raw("files", f"{doc['sha256'][:10]}-{name}", r.content)
    text, problem, pages = extract_text(r.content, ext)
    if pages:
        doc["pages"] = pages
    if problem:
        doc["text_problem"] = problem
        ctx.report["text_problems"].append({"owner": owner_id, "url": url, "problem": problem})
    return text


PAGE_SELECTORS = [".entry-content", "main#main-content", "main", "#main-content", "#main", "article", "[role=main]"]


def process_linked_page(ctx: Ctx, owner_id: str, doc: dict) -> Optional[str]:
    """Fetch an NAU web page that holds a policy ('View the Policy' -> another site) and return its text."""
    from bs4 import BeautifulSoup
    from .util import strip_comments, to_markdown
    url = doc["url"]
    host = urlparse(url).netloc.lower()
    domains = ctx.cfg["documents"].get("page_domains", ["nau.edu"])
    if not any(host == d or host.endswith("." + d) for d in domains):
        doc["note"] = "external host: link only"
        return None
    if ctx.args.no_documents:
        return None
    r = ctx.fetch.get(url)
    if not r.ok:
        doc["http_status"] = r.status
        ctx.report["broken_documents"].append({"owner": owner_id, "url": url, "status": r.status, "error": r.error})
        return None
    soup = BeautifulSoup(r.text, "html.parser")
    node = next((soup.select_one(s) for s in PAGE_SELECTORS if soup.select_one(s) is not None), soup.body)
    if node is None:
        return None
    for bad in node.select("nav, header, footer, script, style, form, aside, .breadcrumb, .breadcrumbs, .sidebar"):
        bad.decompose()
    strip_comments(node)
    md = to_markdown(node)
    if r.final_url != url:
        doc["final_url"] = r.final_url
    if len(norm(md)) < 200:
        doc["text_problem"] = "linked page has very little text"
        ctx.report["text_problems"].append({"owner": owner_id, "url": url, "problem": doc["text_problem"]})
    doc["sha256"] = sha256(md)
    ctx.save_raw("html/linked", slugify(url, 120) + ".html", str(node))
    return md


def write_document_text(ctx: Ctx, owner_id: str, doc: dict, text: str) -> None:
    sha = doc["sha256"]
    if sha in ctx.doc_text_paths:
        doc["text_file"] = ctx.doc_text_paths[sha]
        return
    path = ctx.data / "documents" / owner_id / (slugify(file_stem(doc["url"]), 80) + ".md")
    front = {"title": doc.get("title") or file_stem(doc["url"]), "owner": owner_id, "role": doc.get("role"),
             "url": doc["url"], "sha256": sha, "bytes": doc.get("bytes"), "pages": doc.get("pages"),
             "text_problem": doc.get("text_problem"), "snapshot": ctx.label, "retrieved": ctx.today}
    note = (f"> Text extracted automatically from [{front['title']}]({doc['url']}) on {ctx.today}. "
            "Layout, tables and numbering may be imperfect; the original file is authoritative.\n\n")
    write_md(path, front, f"# {front['title']}\n\n" + note + text)
    doc["text_file"] = ctx.rel(path)
    ctx.doc_text_paths[sha] = doc["text_file"]


# --------------------------------------------------------------------------- library

def crawl_library(ctx: Ctx, full: bool) -> dict:
    lcfg = ctx.cfg["library"]
    base = lcfg["base"]
    non_policy = set(lcfg["non_policy_slugs"]) | set(lcfg["manuals"])
    bundles = set(lcfg.get("bundles", []))
    info: dict = {"membership": {}, "aliases": [], "under_review": set(), "recent_changes": []}

    # Home page: recent changes + manual sanity check
    r = ctx.fetch.get(base)
    if r.ok:
        home = library.parse_home(r.text, base)
        info["recent_changes"] = home["recent_changes"]
        new_manuals = sorted(set(home["manual_slugs"]) - set(lcfg["manuals"]) - non_policy - {""})
        nav_manuals = [s for s in new_manuals if s not in ("by-subject",)]
        if nav_manuals:
            ctx.report["warnings"].append(f"Home page navigation links pages not in sources.yaml manuals: {nav_manuals}")
        lines = ["# Recent policy changes (from the library home page)", "",
                 f"Captured {ctx.today}. NAU lists these without dates.", ""]
        for item in home["recent_changes"]:
            lines.append(f"- [{item['text']}]({item['url']})" if item["url"] else f"- {item['text']}")
        (ctx.data / "process").mkdir(parents=True, exist_ok=True)
        (ctx.data / "process" / "recent-changes.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    else:
        ctx.report["warnings"].append(f"Library home page failed: {r.status} {r.error}")

    # Open for comment
    ofc = lcfg.get("open_for_comment")
    if ofc:
        r = ctx.fetch.get(base + ofc + "/")
        if r.ok:
            md = library.page_markdown(r.text)
            (ctx.data / "process" / "open-for-comment.md").write_text(
                f"# Policies open for comment\n\nCaptured {ctx.today} from {base + ofc}/\n\n" + md, encoding="utf-8")
            for m in re.finditer(r"\((https?://in\.nau\.edu/university-policy-library/[^)\s]+)\)", md):
                s = library.landing_slug(m.group(1), non_policy)
                if s:
                    info["under_review"].add(s)

    # Manuals
    manuals = ctx.args.manual or lcfg["manuals"]
    manual_items: List[dict] = []
    for m in manuals:
        url = base + m + "/"
        r = ctx.fetch.get(url)
        if not r.ok:
            ctx.report["warnings"].append(f"Manual page {m} failed: {r.status} {r.error}")
            continue
        ctx.save_raw("html/manuals", m + ".html", library.main_html(r.text))
        title, entries = library.parse_manual(r.text, url)
        log(f"  manual {m}: {len(entries)} links")
        for e in entries:
            slug = library.landing_slug(e["url"], non_policy)
            if slug:
                info["membership"].setdefault(slug, [])
                if not any(x["manual"] == title for x in info["membership"][slug]):
                    info["membership"][slug].append({"manual": title, "group": e["group"]})
            else:
                manual_items.append(dict(e, manual=title))

    # Subject index (aliases)
    r = ctx.fetch.get(base + lcfg["by_subject"] + "/")
    if r.ok:
        info["aliases"] = library.parse_by_subject(r.text, base)
    else:
        ctx.report["warnings"].append("By-subject index failed")

    targets = set(info["membership"])
    if full:
        for a in info["aliases"]:
            s = library.landing_slug(a["url"] or "", non_policy)
            if s:
                targets.add(s)
        for rc in info["recent_changes"]:
            s = library.landing_slug(rc["url"] or "", non_policy)
            if s:
                targets.add(s)
    info["crawled"] = {}

    queue = sorted(targets)
    i = 0
    while i < len(queue):
        slug = queue[i]
        i += 1
        url = base + slug + "/"
        log(f"  [{i}/{len(queue)}] {slug}")
        r = ctx.fetch.get(url)
        info["crawled"][slug] = r.status
        if not r.ok:
            ctx.report["dead_pages"].append({"slug": slug, "url": url, "status": r.status, "error": r.error,
                                             "linked_from": "manual" if slug in info["membership"] else "subject index / home"})
            continue
        final_slug = library.landing_slug(r.final_url, non_policy)
        if final_slug and final_slug != slug:
            ctx.report["warnings"].append(f"{slug} redirects to {final_slug}")
        ctx.save_raw("html/library", slug + ".html", library.main_html(r.text))
        rec = library.parse_landing(r.text, url, slug, ctx.today, bundle=slug in bundles)
        if rec is None:
            ctx.report["warnings"].append(f"{slug}: could not find page content")
            continue
        rec["manuals"] = info["membership"].get(slug, [])
        if not rec["manuals"]:
            rec["flags"].append("not listed in any manual (found via subject index or home page)")
        rec["under_review"] = slug in info["under_review"]
        build_library_record(ctx, rec)
        for child in rec.get("children", []):
            if child["link_type"] == "landing":
                s = library.landing_slug(child["url"], non_policy)
                if s and s not in queue:
                    queue.append(s)

    # Pages reached through a bundle (e.g. TRV 540) inherit the bundle's manual
    for rid, r in ctx.records.items():
        target = r["front"].get("see_also")
        if not target or target not in ctx.records:
            continue
        tf = ctx.records[target]["front"]
        parent = ctx.records.get(r["front"]["parent"], {}).get("front", {})
        if not tf.get("manuals"):
            tf["manuals"] = parent.get("manuals") or []
            tf["flags"] = [f for f in tf["flags"] if not f.startswith("not listed in any manual")]
        tf["parent"] = r["front"]["parent"]

    # Items linked from manuals that are not landing pages
    for item in manual_items:
        url = item["url"]
        host = urlparse(url).netloc.lower()
        if file_ext(url) and host.endswith("in.nau.edu"):
            build_direct_document_record(ctx, item)
        else:
            ctx.report["external_links"].append({"manual": item["manual"], "group": item["group"] or "",
                                                 "text": item["text"], "url": url})
    return info


def _doc_section(doc: dict, text: str, today: str, policy_title: str = "") -> str:
    title = doc.get("title") or file_stem(doc["url"])
    if policy_title and re.match(r"(view|click|printable|policy$)", title, re.I):
        title = policy_title + (" (interim policy)" if "interim" in title.lower() else "")
    if doc.get("link_type") == "page":
        return (f"\n\n## Policy text from linked page: {title}\n\n"
                f"> Copied from the web page [{doc['url']}]({doc['url']}) on {today}. "
                "That page is maintained outside the policy library and is authoritative.\n\n"
                + re.sub(r"^(#{1,2}) ", "### ", text, flags=re.M))
    return (f"\n\n## Policy document: {title}\n\n"
            f"> Text extracted automatically from [{title}]({doc['url']}) on {today}. "
            "Layout, tables and numbering may be imperfect; the original file is authoritative.\n\n" + text)


def check_document_dates(rec: dict, doc: dict, text: str) -> None:
    """Record dates printed in the policy PDF and flag disagreement with the web page."""
    from .util import parse_date
    for key, pattern in (("effective_date", r"(?:Effective|Origination) Date\s*:\s*([^\n]{6,30})"),
                         ("last_revised", r"Last Revised\s*:\s*([^\n]{6,30})")):
        m = re.search(pattern, text, re.I)
        if not m:
            continue
        raw = re.split(r"\s{2,}|(?<=\d{4})\s", m.group(1).strip())[0]
        iso = parse_date(raw)
        if not iso:
            continue
        doc.setdefault("document_dates", {})[key] = iso
        page_val = rec.get(key)
        if page_val and re.match(r"\d{4}-", str(page_val)) and page_val != iso:
            rec["flags"].append(f"{key} differs: web page {page_val}, policy document {iso}")
        elif not page_val:
            rec["flags"].append(f"{key} {iso} found only in the policy document")


def build_library_record(ctx: Ctx, rec: dict) -> None:
    rid = "upl/" + rec["slug"]
    inline_text = ""
    text_source = "page" if rec["kind"] == "full_text" else ("bundle index" if rec["kind"] == "bundle" else "page summary")
    docx_stems = {file_stem(d["url"]).lower() for d in rec["documents"] if file_ext(d["url"]) == "docx"}
    for doc in rec["documents"]:
        if file_ext(doc["url"]) == "pdf" and file_stem(doc["url"]).lower() in docx_stems and doc["role"] != "policy":
            doc["note"] = "same document as the .docx version; text taken from the .docx"
            continue
        if doc["role"] == "printable" and rec["kind"] == "full_text":
            doc["note"] = "printable copy of this page; not downloaded"
            continue
        if doc["location"] == "sidebar" and doc["role"] != "policy":
            doc["note"] = "sidebar link; not downloaded"
            continue
        if doc.get("link_type") == "page":
            text = process_linked_page(ctx, rid, doc)
        else:
            text = process_document(ctx, rid, doc)
        if doc["role"] == "draft":
            rec["under_review"] = True
        if not text:
            continue
        if rec["kind"] == "summary" and doc["role"] == "policy" and "inline" not in text_source:
            inline_text += _doc_section(doc, text, ctx.today, rec["title"])
            check_document_dates(rec, doc, text)
            doc["text_file"] = "(inline in policy file)"
            text_source = ("page summary + linked web page (inline)" if doc.get("link_type") == "page"
                           else "page summary + policy document (inline)")
        else:
            write_document_text(ctx, rid, doc, text)
    if rec["kind"] == "summary" and "inline" not in text_source:
        ext = next((d for d in rec["documents"] if d["role"] == "policy" and d.get("note", "").startswith("external")), None)
        if ext:
            text_source = "page summary; policy hosted outside NAU sites"
            rec["flags"].append(f"policy text lives on an external site: {ext['url']}")
        elif rec.get("draft_only"):
            text_source = "page summary only (draft document stored separately)"
        else:
            rec["flags"].append("full policy text not captured (document missing or not downloaded)")

    body = f"# {rec['title']}\n\n" + rec["body_md"] + inline_text
    front = {
        "id": rid,
        "title": rec["title"],
        "source": "university-policy-library",
        "kind": rec["kind"],
        "status": rec["status"],
        "superseded_by": rec.get("superseded_by"),
        "under_review": rec.get("under_review") or None,
        "official_number": rec.get("official_number"),
        "manuals": rec["manuals"],
        "responsible_executive": rec.get("responsible_executive"),
        "responsible_office": rec.get("responsible_office"),
        "contact": rec.get("contact"),
        "contact_email": rec.get("contact_email"),
        "effective_date": rec.get("effective_date"),
        "effective_date_label": rec.get("effective_date_label"),
        "effective_date_as_published": rec.get("effective_date_as_published"),
        "last_revised": rec.get("last_revised"),
        "last_revised_as_published": rec.get("last_revised_as_published"),
        "history": rec.get("history"),
        "who_should_know": rec.get("who_should_know"),
        "entities_affected": rec.get("entities_affected"),
        "keywords": rec.get("keywords"),
        "sections": rec.get("sections"),
        "text_source": text_source,
        "url": rec["url"],
        "printable_pdf": rec.get("printable_pdf"),
        "documents": rec["documents"],
        "related": rec.get("related"),
        "content_sha256": sha256(body),
        "snapshot": ctx.label,
        "retrieved": ctx.today,
        "flags": rec["flags"],
    }
    if rec["kind"] == "bundle":
        front["children"] = []
    ctx.records[rid] = {"front": front, "body": body, "path": ctx.data / "policies" / (rid + ".md")}

    if rec["kind"] == "bundle":
        used = set()
        for child in rec.get("children", []):
            cslug = slugify(child["code"] or child["title"], 50)
            while cslug in used:
                cslug += "-x"
            used.add(cslug)
            cid = f"{rid}/{cslug}"
            front["children"].append(cid)
            build_bundle_child(ctx, rec, child, cid)


def build_bundle_child(ctx: Ctx, parent: dict, child: dict, cid: str) -> None:
    title = (f"{child['code']} " if child["code"] else "") + child["title"]
    front = {
        "id": cid,
        "title": title,
        "source": "university-policy-library",
        "kind": "bundle_item",
        "status": "active",
        "parent": "upl/" + parent["slug"],
        "parent_title": parent["title"],
        "official_number": child["code"],
        "manuals": parent.get("manuals"),
        "group": " / ".join(x for x in (child["section"], child["subgroup"]) if x),
        "url": parent["url"],
        "documents": [],
        "snapshot": ctx.label,
        "retrieved": ctx.today,
        "flags": [],
    }
    body = (f"# {title}\n\n> Part of [{parent['title']}]({parent['url']})"
            + (f", {front['group']}" if front["group"] else "") + ".\n")
    if child["link_type"] == "file":
        doc = {"url": child["url"], "title": title, "role": "policy", "location": "body"}
        front["documents"].append(doc)
        text = process_document(ctx, cid, doc)
        if text:
            body += _doc_section(doc, text, ctx.today, title)
            front["text_source"] = "policy document"
        else:
            front["flags"].append("policy text not captured")
    elif child["link_type"] == "landing":
        front["see_also"] = "upl/" + child["url"].rstrip("/").rsplit("/", 1)[-1]
        body += f"\nThis item has its own page: {child['url']}\n"
        front["text_source"] = "see_also"
    else:
        body += f"\nLink: {child['url']}\n"
    front["content_sha256"] = sha256(body)
    ctx.records[cid] = {"front": front, "body": body, "path": ctx.data / "policies" / (cid + ".md")}


def build_direct_document_record(ctx: Ctx, item: dict) -> None:
    rid = "upl/doc-" + slugify(item["text"] or file_stem(item["url"]), 50)
    doc = {"url": item["url"], "title": item["text"], "role": "policy", "location": "body"}
    front = {"id": rid, "title": item["text"], "source": "university-policy-library", "kind": "document_only",
             "status": "active", "manuals": [{"manual": item["manual"], "group": item["group"]}],
             "url": item["url"], "documents": [doc], "snapshot": ctx.label, "retrieved": ctx.today,
             "flags": ["linked from a manual directly as a file; no landing page or metadata"]}
    body = f"# {item['text']}\n"
    text = process_document(ctx, rid, doc)
    if text:
        body += _doc_section(doc, text, ctx.today, item["text"])
        front["text_source"] = "policy document"
    front["content_sha256"] = sha256(body)
    ctx.records[rid] = {"front": front, "body": body, "path": ctx.data / "policies" / (rid + ".md")}


# --------------------------------------------------------------------------- academic catalog

def crawl_academic(ctx: Ctx) -> None:
    acfg = ctx.cfg["academic_catalog"]
    base = acfg["base"]
    rows: Dict[str, dict] = {}
    for page in range(1, 40):
        url = academic.index_url(base, page)
        r = ctx.fetch.get(url)
        if not r.ok:
            if page == 1:
                ctx.report["warnings"].append(f"Academic catalog index failed: {r.status} {r.error}")
            break
        if page == 1:
            ctx.save_raw("html/academic", "index-page1.html", r.text)
        new = [x for x in academic.parse_index(r.text, url) if x["number"] not in rows]
        if not new:
            break
        for x in new:
            rows[x["number"]] = x
    log(f"  academic catalog index: {len(rows)} policies")

    audience: Dict[str, List[str]] = {}
    for code, name in (acfg.get("audiences") or {}).items():
        found = set()
        for page in range(1, 40):
            r = ctx.fetch.get(academic.index_url(base, page, int(code)))
            if not r.ok:
                break
            new = {x["number"] for x in academic.parse_index(r.text, "")} - found
            if not new:
                break
            found |= new
        if not found or len(found) >= len(rows):
            ctx.report["warnings"].append(f"Audience filter '{name}' returned {len(found)} of {len(rows)}; not used")
            continue
        for n in found:
            audience.setdefault(n, []).append(name)

    numbers = sorted(rows)
    if ctx.args.academic_limit:
        numbers = numbers[: ctx.args.academic_limit]
    for i, num in enumerate(numbers, 1):
        row = rows[num]
        url = academic.detail_url(base, row["internal_id"])
        log(f"  [{i}/{len(numbers)}] academic {num} {row['title'][:50]}")
        r = ctx.fetch.get(url)
        if not r.ok:
            ctx.report["dead_pages"].append({"slug": f"academic {num}", "url": url, "status": r.status, "error": r.error,
                                             "linked_from": "academic catalog index"})
            continue
        rec = academic.parse_detail(r.text, url)
        if rec is None:
            ctx.report["warnings"].append(f"academic {num}: could not parse")
            continue
        ctx.save_raw("html/academic", f"{num}.html", rec.pop("main_html"))
        if rec.get("number") and rec["number"] != num:
            rec["flags"].append(f"index lists {num} but page shows {rec['number']}")
        if row["begin_date"] and rec.get("effective_date") and row["begin_date"] != rec["effective_date"]:
            rec["flags"].append(f"index begin date {row['begin_date']} differs from page {rec['effective_date']}")
        futures = []
        for fv in row["future_versions"]:
            fr = ctx.fetch.get(academic.detail_url(base, fv["internal_id"]))
            if fr.ok:
                frec = academic.parse_detail(fr.text, fr.url)
                if frec:
                    frec.pop("main_html", None)
                    futures.append(frec)
        build_academic_record(ctx, num, row, rec, audience.get(num, []), futures)


def build_academic_record(ctx: Ctx, num: str, row: dict, rec: dict, audience: List[str], futures: List[dict]) -> None:
    rid = "acad/" + num
    title = rec.get("title") or row["title"]
    body = f"# {num} {title}\n\n" + rec["body_md"]
    if rec.get("related"):
        body += "\n## Related policies\n\n" + "\n".join(f"- [{x['text']}]({x['url']})" for x in rec["related"]) + "\n"
    front = {
        "id": rid,
        "title": title,
        "source": "academic-catalog",
        "kind": "full_text",
        "status": "active",
        "official_number": num,
        "type": rec.get("type"),
        "audience": audience or None,
        "effective_date": rec.get("effective_date"),
        "appeal_eligible": rec.get("appeal_eligible"),
        "petition_eligible": rec.get("petition_eligible"),
        "fees_may_apply": rec.get("fees_may_apply"),
        "who_should_know": rec.get("who_should_know"),
        "entities_affected": rec.get("entities_affected"),
        "sections": rec.get("sections"),
        "text_source": "page",
        "url": rec["url"],
        "internal_version_id": row["internal_id"],
        "related": rec.get("related"),
        "future_versions": [{"effective_date": f.get("effective_date"), "url": f["url"]} for f in futures] or None,
        "content_sha256": sha256(body),
        "snapshot": ctx.label,
        "retrieved": ctx.today,
        "flags": rec["flags"],
    }
    for f in futures:
        body += (f"\n\n---\n\n# Future version effective {f.get('effective_date')}\n\n"
                 f"Source: {f['url']}\n\n" + f["body_md"])
    ctx.records[rid] = {"front": front, "body": body, "path": ctx.data / "policies" / (rid + ".md")}


# --------------------------------------------------------------------------- orchestration

def catalog_row(rec: dict, root: Path) -> dict:
    f = rec["front"]
    manuals = [m["manual"] for m in (f.get("manuals") or []) if m.get("manual")]
    group = f.get("group") or next((m.get("group") for m in (f.get("manuals") or []) if m.get("group")), None)
    return {
        "id": f["id"], "source": f["source"], "title": f["title"], "official_number": f.get("official_number"),
        "kind": f["kind"], "status": f["status"], "under_review": bool(f.get("under_review")),
        "manuals": manuals, "group": group, "effective_date": f.get("effective_date"),
        "last_revised": f.get("last_revised"), "type": f.get("type"), "audience": f.get("audience"),
        "who_should_know": f.get("who_should_know"), "keywords": f.get("keywords"),
        "responsible_office": f.get("responsible_office"), "url": f["url"],
        "path": rec["path"].relative_to(root).as_posix(), "text_source": f.get("text_source"),
        "content_sha256": f["content_sha256"],
        "doc_hashes": {d["url"]: d["sha256"] for d in f.get("documents") or [] if d.get("sha256")},
        "flags": f.get("flags"), "snapshot": f["snapshot"],
    }


def resolve_aliases(ctx: Ctx, info: dict) -> List[dict]:
    non_policy = set(ctx.cfg["library"]["non_policy_slugs"]) | set(ctx.cfg["library"]["manuals"])
    out = []
    for a in info.get("aliases", []):
        url = a["url"] or ""
        slug = library.landing_slug(url, non_policy)
        status, target = "", ""
        if not url:
            status = "no link"
        elif slug:
            st = info["crawled"].get(slug)
            if "upl/" + slug in ctx.records:
                status, target = "ok", "upl/" + slug
            elif st is None:
                status = "not checked this run"
            else:
                status = f"dead ({st})"
        elif "www9.nau.edu/policies" in url:
            status = "academic catalog"
        else:
            status = "external"
        out.append({"letter": a["letter"], "term": a["term"], "target_id": target, "status": status, "url": url})
    return out


def run(root: Path, args) -> int:
    cfg = yaml.safe_load((root / "sources.yaml").read_text(encoding="utf-8"))
    label = args.label or _dt.date.today().strftime("%Y-%m")
    ctx = Ctx(root, cfg, label, args)
    if args.pilot:
        args.manual = args.manual or ["academic-faculty-affairs"]
    full = not args.manual and not args.no_library and not args.no_academic and not args.academic_limit
    scope = []
    if not args.no_library:
        scope.append("library: " + (", ".join(args.manual) if args.manual else "all manuals + subject index"))
    if not args.no_academic:
        scope.append("academic catalog" + (f" (first {args.academic_limit})" if args.academic_limit else ""))
    if args.no_documents:
        scope.append("documents not downloaded")
    scope_desc = "; ".join(scope)
    log(f"Snapshot {label} — {scope_desc}")

    prev_path = root / "data" / "catalog.json"
    prev = json.loads(prev_path.read_text(encoding="utf-8")) if prev_path.exists() else {}

    info: dict = {"aliases": [], "crawled": {}}
    if not args.no_library:
        log("University Policy Library…")
        info = crawl_library(ctx, full)
    if not args.no_academic:
        log("Academic Catalog…")
        crawl_academic(ctx)

    # Write
    if full:
        for sub in ("policies", "documents"):
            shutil.rmtree(ctx.data / sub, ignore_errors=True)
    for rid, rec in ctx.records.items():
        write_md(rec["path"], rec["front"], rec["body"])
    cur = {rid: catalog_row(rec, root) for rid, rec in ctx.records.items()}
    merged = dict(cur) if full else {**prev, **cur}
    write_catalog(root, merged)
    write_index(root, merged, label)
    if not args.no_library:
        write_csv(ctx.data / "aliases.csv", resolve_aliases(ctx, info),
                  ["letter", "term", "target_id", "status", "url"])
        if ctx.report["external_links"]:
            write_csv(ctx.data / "external_links.csv", ctx.report["external_links"], ["manual", "group", "text", "url"])
    prepend_changelog(root, changelog_entry(prev, merged, label, ctx.today, full, scope_desc))
    write_run_report(ctx, cur, scope_desc)
    log(f"Done: {len(cur)} records written. See data/runs/{label}.md")
    return 0


def write_run_report(ctx: Ctx, cur: Dict[str, dict], scope_desc: str) -> None:
    from collections import Counter
    rep = ctx.report
    kinds = Counter((r["source"], r["kind"]) for r in cur.values())
    lines = [f"# Run report: {ctx.label}", "", f"Run date: {ctx.today}  ", f"Scope: {scope_desc}  ",
             f"HTTP requests: {len(ctx.fetch.log)}", "", "## Records", "", "| source | kind | count |", "|---|---|---|"]
    for (s, k), n in sorted(kinds.items()):
        lines.append(f"| {s} | {k} | {n} |")
    flagged = [r for r in cur.values() if r.get("flags")]
    lines += ["", f"## Flags ({len(flagged)} records)", ""]
    for r in sorted(flagged, key=lambda r: r["id"]):
        lines.append(f"- `{r['id']}` {r['title']}: " + "; ".join(r["flags"]))
    def table(title, items, cols):
        nonlocal lines
        lines += ["", f"## {title} ({len(items)})", ""]
        if items:
            lines += ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
            for it in items:
                lines.append("| " + " | ".join(str(it.get(c, "")).replace("|", "/") for c in cols) + " |")
    table("Dead or failing pages", rep["dead_pages"], ["slug", "status", "linked_from", "url"])
    table("Broken document links", rep["broken_documents"], ["owner", "status", "url"])
    table("Text extraction problems", rep["text_problems"], ["owner", "problem", "url"])
    lines += ["", f"## Warnings ({len(rep['warnings'])})", ""] + [f"- {w}" for w in rep["warnings"]]
    p = ctx.data / "runs" / f"{ctx.label}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
