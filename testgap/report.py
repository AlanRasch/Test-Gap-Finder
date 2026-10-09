"""Output formats: plain text for the terminal, Markdown for pull requests, JSON for other tools."""

from __future__ import annotations

import json

from .analyzer import Report, level


def _summary_lines(report: Report) -> list[str]:
    lines = [
        f"Functions analysed: {report.total}",
        f"Tested: {report.tested_count} ({report.percent}%)",
        f"Untested: {len(report.untested)}",
        f"Evidence used: {report.mode}",
        f"Test files found: {report.test_files}",
        f"Git churn used: {'yes' if report.churn_used else 'no'}",
    ]
    lines.extend(f"Warning: {w}" for w in report.warnings)
    return lines


def render_text(report: Report, top: int = 25) -> str:
    out = [f"Test-Gap Finder report for {report.root}", ""]
    out.extend(_summary_lines(report))
    untested = report.untested
    if not untested:
        out.append("\nEvery analysed function is exercised by the tests.")
        return "\n".join(out)

    out.append("\nUntested functions, highest risk first:\n")
    out.append(f"{'Risk':>6}  {'Level':<7}{'Function':<34}{'Location':<30}{'Cx':>4}")
    for finding in untested[:top]:
        fn = finding.function
        location = f"{fn.file}:{fn.lineno}"
        out.append(f"{finding.risk:>6}  {level(finding.risk):<7}{fn.qualname:<34}{location:<30}{fn.complexity:>4}")
    if len(untested) > top:
        out.append(f"\n... and {len(untested) - top} more. Use --top N or --format markdown to see them all.")
    out.append("\nCx = complexity (number of decision points plus one). Higher means more paths to test.")
    return "\n".join(out)


def render_markdown(report: Report, top: int | None = None) -> str:
    out = ["# Test-Gap Report", ""]
    out.append(f"- Project: `{report.root}`")
    out.append(f"- Functions analysed: **{report.total}**")
    out.append(f"- Tested: **{report.tested_count}** ({report.percent}%)")
    out.append(f"- Untested: **{len(report.untested)}**")
    out.append(f"- Evidence used: {report.mode}")
    for warning in report.warnings:
        out.append(f"- Warning: {warning}")
    untested = report.untested
    if not untested:
        out.append("\nEvery analysed function is exercised by the tests.")
        return "\n".join(out) + "\n"

    out.append("\n## Untested functions, highest risk first\n")
    out.append("| Risk | Level | Function | Location | Complexity |")
    out.append("|---:|---|---|---|---:|")
    rows = untested if top is None else untested[:top]
    for finding in rows:
        fn = finding.function
        out.append(f"| {finding.risk} | {level(finding.risk)} | `{fn.qualname}` | `{fn.file}:{fn.lineno}` | {fn.complexity} |")
    out.append("\nSuggested next step: add a test for the top items first, then re-run `test-gap scan`.")
    return "\n".join(out) + "\n"


def render_json(report: Report, top: int | None = None) -> str:
    data = {
        "root": report.root,
        "summary": {
            "functions": report.total,
            "tested": report.tested_count,
            "untested": len(report.untested),
            "percent_tested": report.percent,
            "evidence": report.mode,
            "test_files": report.test_files,
        },
        "warnings": report.warnings,
        "findings": [f.to_dict() for f in report.findings],
    }
    return json.dumps(data, indent=2)
