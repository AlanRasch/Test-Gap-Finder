"""Command-line interface.

  test-gap scan     show untested functions ranked by risk
  test-gap draft    write starter test files for the riskiest untested functions
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from .analyzer import analyze
from .drafter import write_drafts
from .report import render_json, render_markdown, render_text


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", default=".", help="project folder (default: current folder)")
    parser.add_argument("--source", action="append",
                        help="folder with source code, relative to --root; repeat for several "
                             "(default: src if it exists, otherwise the whole project)")
    parser.add_argument("--tests", default="tests", help="folder with test files (default: tests)")
    parser.add_argument("--coverage", help="coverage.json file from 'coverage json' (more accurate)")
    parser.add_argument("--churn", action="store_true",
                        help="raise the risk of files changed often in git (last 180 days)")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="test-gap", description="Find the untested functions that matter most.")
    sub = p.add_subparsers(dest="cmd", required=True)

    scan = sub.add_parser("scan", help="list untested functions, highest risk first")
    _common(scan)
    scan.add_argument("--format", choices=["text", "markdown", "json"], default="text")
    scan.add_argument("-o", "--output", help="write the report to a file instead of printing it")
    scan.add_argument("--top", type=int, default=25, help="rows to show in text output (default 25)")
    scan.add_argument("--fail-under", type=float, metavar="PERCENT",
                      help="exit with code 1 if the tested percentage is below this value (for CI)")

    draft = sub.add_parser("draft", help="write starter test files for untested functions")
    _common(draft)
    draft.add_argument("--limit", type=int, default=10, help="how many functions to draft (default 10)")
    draft.add_argument("--out", help="folder for the new test files (default: the tests folder)")
    draft.add_argument("--with-claude", action="store_true",
                       help="let Claude write the tests (needs ANTHROPIC_API_KEY)")
    draft.add_argument("--model", default=os.getenv("TG_MODEL", "claude-sonnet-5-5"))
    return p


def _make_client():
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        raise ValueError("--with-claude needs ANTHROPIC_API_KEY. Set it in your environment or in a .env file.")
    import anthropic  # imported only when needed
    return anthropic.Anthropic(api_key=key)


def _scan(args, report) -> int:
    renderers = {"text": render_text, "markdown": render_markdown, "json": render_json}
    text = renderers[args.format](report, args.top)
    if args.output:
        Path(args.output).write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        print(text)
    if args.fail_under is not None and report.percent < args.fail_under:
        print(f"Tested {report.percent}% is below the required {args.fail_under}%.", file=sys.stderr)
        return 1
    return 0


def _draft(args, report, root: Path) -> int:
    client = _make_client() if args.with_claude else None
    out_dir = Path(args.out) if args.out and Path(args.out).is_absolute() else root / (args.out or args.tests)
    written, skipped = write_drafts(report, out_dir, args.limit, client, args.model)
    for path in written:
        print(f"Created {path}")
    for path in skipped:
        print(f"Skipped {path.name}: the file already exists and is never overwritten.")
    if not written and not skipped:
        print("No untested functions to draft tests for.")
    elif written:
        print("\nNext: fill in the TODO tests (or review the AI drafts), then run: pytest")
    return 0


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve()
    try:
        if not root.is_dir():
            raise ValueError(f"Project folder not found: {root}")
        report = analyze(root, args.source, args.tests, args.coverage, args.churn)
        if args.cmd == "scan":
            return _scan(args, report)
        return _draft(args, report, root)
    except (OSError, ValueError, SyntaxError, json.JSONDecodeError) as err:
        print(f"Error: {err}", file=sys.stderr)
        return 2
