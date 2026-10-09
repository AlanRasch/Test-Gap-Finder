"""Write starter test files for untested functions.

Default: a skeleton per function that is marked as skipped until you fill it in.
With --with-claude: an AI model drafts real tests from each function's source.
Either way, existing files are never overwritten and nothing is run for you.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from .analyzer import Finding, Function, Report


def module_name(file: str, source_dirs: list[str]) -> str:
    """'src/shop/cart.py' with source folder 'src' -> 'shop.cart'."""
    path = Path(file)
    rel = path
    for base in source_dirs:
        if base in (".", ""):
            rel = path
            break
        try:
            rel = path.relative_to(base)
            break
        except ValueError:
            continue
    parts = list(rel.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _test_name(fn: Function) -> str:
    return "test_" + fn.qualname.replace(".", "_").lower() + "_draft"


def skeleton_for(fn: Function) -> str:
    lines = [
        f"def {_test_name(fn)}():",
        f'    """Check {fn.qualname} ({fn.file}:{fn.lineno}, complexity {fn.complexity})."""',
    ]
    if fn.is_method:
        lines.append(f"    # Create a {fn.target} object first, then call the method.")
    lines.append(f'    pytest.skip("TODO: call {fn.qualname} with real inputs and assert the result")')
    return "\n".join(lines)


def _strip_fences(text: str) -> str:
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("python"):
            text = text[len("python"):]
    return text.strip("\n")


def claude_test(fn: Function, source_path: Path, module: str, client, model: str) -> str:
    lines = source_path.read_text(encoding="utf-8").splitlines()
    snippet = "\n".join(lines[fn.lineno - 1: fn.end_lineno])
    prompt = (
        f"Write 2 or 3 pytest test functions for the Python function `{fn.qualname}` "
        f"from module `{module}`. Use realistic inputs and clear assertions. "
        "Do not write import statements. Return only Python code, with no explanation and no markdown.\n\n"
        f"{snippet}"
    )
    response = client.messages.create(
        model=model, max_tokens=1500, messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(block.text for block in response.content if getattr(block, "type", "") == "text")
    return _strip_fences(text)


def _file_body(module: str, functions: list[Function], bodies: list[str], drafted_by_ai: bool) -> str:
    targets = sorted({fn.target for fn in functions})
    header = []
    if drafted_by_ai:
        header.append("# Drafted by an AI model with test-gap. Review every test before you rely on it.")
    else:
        header.append("# Skeleton tests written by test-gap. Replace each skip with a real assertion.")
    header.append("import pytest")
    if module:
        header.append(f"from {module} import {', '.join(targets)}")
    return "\n".join(header) + "\n\n\n" + "\n\n\n".join(bodies) + "\n"


def write_drafts(report: Report, out_dir: Path, limit: int = 10, client=None,
                 model: str = "claude-sonnet-5-5") -> tuple[list[Path], list[Path]]:
    """Write one test file per source file. Returns (written, skipped_because_it_exists)."""
    root = Path(report.root)
    chosen: list[Finding] = report.untested[:limit]
    groups: dict[str, list[Function]] = defaultdict(list)
    for finding in chosen:
        groups[finding.function.file].append(finding.function)

    written: list[Path] = []
    skipped: list[Path] = []
    for file, functions in groups.items():
        module = module_name(file, report.source_dirs)
        stem = Path(file).with_suffix("").as_posix().replace("/", "_")
        target = out_dir / f"test_gaps_{stem}.py"
        if target.exists():
            skipped.append(target)
            continue
        if client is not None:
            bodies = [claude_test(fn, root / file, module, client, model) for fn in functions]
        else:
            bodies = [skeleton_for(fn) for fn in functions]
        out_dir.mkdir(parents=True, exist_ok=True)
        target.write_text(_file_body(module, functions, bodies, drafted_by_ai=client is not None), encoding="utf-8")
        written.append(target)
    return written, skipped
