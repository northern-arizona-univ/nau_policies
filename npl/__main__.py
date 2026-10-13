"""Command line: python3 -m npl crawl [options]"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python3 -m npl", description="Snapshot NAU policies into data/.")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("crawl", help="fetch policies and write a snapshot")
    c.add_argument("--label", help="snapshot label, e.g. 2026-fall (default: YYYY-MM)")
    c.add_argument("--pilot", action="store_true",
                   help="test run: Academic & Faculty Affairs manual + the academic catalog")
    c.add_argument("--manual", action="append", metavar="SLUG",
                   help="only crawl this manual (repeatable), e.g. human-resources")
    c.add_argument("--no-library", action="store_true", help="skip the University Policy Library")
    c.add_argument("--no-academic", action="store_true", help="skip the Academic Catalog policies")
    c.add_argument("--academic-limit", type=int, metavar="N", help="only the first N academic policies")
    c.add_argument("--no-documents", action="store_true", help="do not download PDFs/Word files")
    c.add_argument("--delay", type=float, help="seconds between requests (default from sources.yaml)")
    args = p.parse_args(argv)

    root = Path(__file__).resolve().parent.parent
    if args.cmd == "crawl":
        from .crawl import run
        return run(root, args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
