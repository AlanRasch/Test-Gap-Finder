"""Find functions that the test suite does not exercise, and rank them by risk.

Two kinds of evidence are supported:

* Name matching (default, no setup needed): a function counts as tested when a
  test file mentions its name. Fast and simple, but it can be fooled by common
  names such as "run" or "get".
* Coverage data (recommended): pass a coverage.json file made with
  `coverage run -m pytest` followed by `coverage json`. A function counts as
  tested only when at least one of its lines actually ran during the tests.
"""

from __future__ import annotations

import ast
import json
import subprocess
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

EXCLUDED_DIRS = {
    ".git", ".venv", "venv", "env", "build", "dist", "node_modules", "__pycache__",
    "site-packages", ".tox", ".mypy_cache", ".pytest_cache", "tests", "test",
}
TEST_FILE_PATTERNS = ("test_*.py", "*_test.py")
SKIPPED_FILES = {"conftest.py", "setup.py"}


# ---------- data ----------

@dataclass
class Function:
    file: str          # path relative to the project root, with forward slashes
    qualname: str      # "add" for a function, "Cart.total" for a method
    target: str        # name to import: the function, or the class for a method
    lineno: int
    end_lineno: int
    complexity: int
    churn: int = 0     # number of git commits touching the file (0 if not measured)
    body_lineno: int = 0  # first line of the body; coverage only counts body lines (the def line runs on import)

    @property
    def name(self) -> str:
        return self.qualname.rsplit(".", 1)[-1]

    @property
    def lines(self) -> int:
        return self.end_lineno - self.lineno + 1

    @property
    def is_method(self) -> bool:
        return "." in self.qualname


@dataclass
class Finding:
    function: Function
    risk: float
    tested: bool
    evidence: str      # "coverage", "name" or "none"

    def to_dict(self) -> dict:
        data = asdict(self.function)
        data.update({"name": self.function.name, "lines": self.function.lines, "risk": self.risk,
                     "tested": self.tested, "evidence": self.evidence, "level": level(self.risk)})
        return data


@dataclass
class Report:
    root: str
    findings: list[Finding]
    source_dirs: list[str]
    test_files: int
    mode: str                      # "coverage" or "test names"
    churn_used: bool
    source_files: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.findings)

    @property
    def tested_count(self) -> int:
        return sum(1 for f in self.findings if f.tested)

    @property
    def percent(self) -> float:
        return round(100 * self.tested_count / self.total, 1) if self.total else 100.0

    @property
    def untested(self) -> list[Finding]:
        return [f for f in self.findings if not f.tested]


# ---------- scoring ----------

def level(risk: float) -> str:
    if risk >= 20:
        return "High"
    if risk >= 10:
        return "Medium"
    return "Low"


def risk_score(fn: Function) -> float:
    """More branches, more lines and more frequent changes mean more risk."""
    return round(fn.complexity * 2 + fn.lines / 10 + min(fn.churn, 30) / 3, 1)


def complexity_of(node: ast.AST) -> int:
    """Rough cyclomatic complexity: 1 plus one for each decision point."""
    score = 1
    for sub in ast.walk(node):
        if sub is node:
            continue
        if isinstance(sub, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.IfExp, ast.ExceptHandler)):
            score += 1
        elif isinstance(sub, ast.BoolOp):
            score += len(sub.values) - 1
        elif isinstance(sub, ast.comprehension):
            score += 1 + len(sub.ifs)
    return score


# ---------- discovery ----------

def default_source_dirs(root: Path) -> list[Path]:
    return [root / "src"] if (root / "src").is_dir() else [root]


def discover_sources(root: Path, source_dirs: list[Path]) -> list[Path]:
    files: set[Path] = set()
    for base in source_dirs:
        for path in base.rglob("*.py"):
            parts = path.relative_to(root).parts
            if any(part in EXCLUDED_DIRS for part in parts[:-1]):
                continue
            if path.name in SKIPPED_FILES or any(path.match(p) for p in TEST_FILE_PATTERNS):
                continue
            files.add(path)
    return sorted(files)


def discover_tests(test_dir: Path) -> list[Path]:
    if not test_dir.is_dir():
        return []
    found: set[Path] = set()
    for pattern in TEST_FILE_PATTERNS:
        found.update(test_dir.rglob(pattern))
    return sorted(found)


def parse_functions(path: Path, root: Path, churn: dict[str, int] | None = None) -> list[Function]:
    """List the public functions and methods in one file. Names starting with _ are skipped."""
    rel = path.relative_to(root).as_posix()
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[Function] = []

    def visit(body: list[ast.stmt], prefix: str, owner: str | None) -> None:
        for node in body:
            if isinstance(node, ast.ClassDef):
                if not node.name.startswith("_"):
                    visit(node.body, prefix + node.name + ".", owner or node.name)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("_"):
                    continue
                found.append(Function(
                    file=rel,
                    qualname=prefix + node.name,
                    target=owner or node.name,
                    lineno=node.lineno,
                    end_lineno=node.end_lineno or node.lineno,
                    complexity=complexity_of(node),
                    churn=(churn or {}).get(rel, 0),
                    body_lineno=node.body[0].lineno if node.body else node.lineno,
                ))

    visit(tree.body, "", None)
    return found


def referenced_names(test_files: list[Path]) -> set[str]:
    """Every name, attribute and imported name that appears in the test files."""
    names: set[str] = set()
    for path in test_files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                names.add(node.id)
            elif isinstance(node, ast.Attribute):
                names.add(node.attr)
            elif isinstance(node, ast.ImportFrom):
                names.update(alias.name for alias in node.names)
    return names


def load_coverage(path: Path, root: Path) -> dict[str, set[int]]:
    """Map each file (relative to root) to the set of line numbers that ran."""
    data = json.loads(path.read_text(encoding="utf-8"))
    executed: dict[str, set[int]] = {}
    for filename, info in data.get("files", {}).items():
        p = Path(filename)
        if p.is_absolute():
            try:
                p = p.resolve().relative_to(root)
            except ValueError:
                continue
        executed[p.as_posix()] = set(info.get("executed_lines", []))
    return executed


def git_churn(root: Path, days: int = 180) -> dict[str, int]:
    """How many commits touched each Python file in the last `days` days. Empty if git is unavailable."""
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "log", f"--since={days} days ago", "--name-only", "--pretty=format:"],
            capture_output=True, text=True, timeout=60, check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    return dict(Counter(line.strip() for line in out.splitlines() if line.strip().endswith(".py")))


# ---------- main entry point ----------

def analyze(root: str | Path, source_dirs: list[str] | None = None, test_dir: str = "tests",
            coverage: str | Path | None = None, use_churn: bool = False, days: int = 180) -> Report:
    root = Path(root).resolve()
    sources = [root / d for d in source_dirs] if source_dirs else default_source_dirs(root)
    tests = discover_tests(root / test_dir)
    warnings: list[str] = []
    if not tests:
        warnings.append(f"No test files found in '{test_dir}'. Every function is reported as untested.")

    churn = git_churn(root, days) if use_churn else {}
    cov = None
    if coverage:
        cov_path = Path(coverage)
        cov_path = cov_path if cov_path.is_absolute() else root / cov_path
        cov = load_coverage(cov_path, root)

    names = referenced_names(tests)
    source_files = discover_sources(root, sources)
    functions = [fn for path in source_files for fn in parse_functions(path, root, churn)]

    findings: list[Finding] = []
    for fn in functions:
        if cov is not None:
            ran = cov.get(fn.file, set())
            executed = any(line in ran for line in range(fn.body_lineno, fn.end_lineno + 1))
            evidence = "coverage" if executed else "none"
            tested = executed
        else:
            named = fn.name in names
            evidence = "name" if named else "none"
            tested = named
        findings.append(Finding(fn, risk_score(fn), tested, evidence))

    findings.sort(key=lambda f: (f.tested, -f.risk, f.function.file, f.function.lineno))
    rel_sources = [p.relative_to(root).as_posix() if p != root else "." for p in sources]
    return Report(
        root=str(root),
        findings=findings,
        source_dirs=[s for s in rel_sources],
        test_files=len(tests),
        mode="coverage data" if cov is not None else "test names",
        churn_used=use_churn,
        source_files=len(source_files),
        warnings=warnings,
    )
