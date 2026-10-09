"""Offline tests for test-gap. Run with:  python -m pytest -q"""

import json
from pathlib import Path

import pytest

from testgap.analyzer import analyze, complexity_of, level, load_coverage, parse_functions, risk_score
from testgap.cli import main
from testgap.drafter import module_name, write_drafts
from testgap.report import render_json, render_markdown, render_text

DEMO = Path(__file__).resolve().parent.parent / "examples" / "demo_project"

CALC = '''\
def add(a, b):
    return a + b


def classify(n):
    if n < 0:
        return "negative"
    elif n == 0:
        return "zero"
    return "positive" if n > 10 else "small"


class Cart:
    def __init__(self):
        self.items = []

    def total(self):
        return sum(self.items)

    def add(self, x):
        self.items.append(x)


def _private_helper():
    return 1
'''


@pytest.fixture
def project(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "calc.py").write_text(CALC)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_calc.py").write_text("from calc import add\n\ndef test_add():\n    assert add(1, 2) == 3\n")
    return tmp_path


def _by_name(report):
    return {f.function.qualname: f for f in report.findings}


def test_finds_public_functions_and_methods_only(project):
    names = set(_by_name(analyze(project)))
    assert names == {"add", "classify", "Cart.total", "Cart.add"}  # private and __init__ skipped


def test_name_matching_marks_tested_functions(project):
    found = _by_name(analyze(project))
    assert found["add"].tested and found["add"].evidence == "name"
    assert not found["classify"].tested and found["classify"].evidence == "none"


def test_untested_come_first_sorted_by_risk(project):
    report = analyze(project)
    untested_risks = [f.risk for f in report.untested]
    assert untested_risks == sorted(untested_risks, reverse=True)
    assert report.findings[0].tested is False


def test_coverage_mode_is_stricter_than_name_matching(project):
    # add() ran, but Cart.add (same name, never executed) must not count as tested.
    cov = {"files": {"src/calc.py": {"executed_lines": [1, 2, 3]}}}
    (project / "coverage.json").write_text(json.dumps(cov))
    found = _by_name(analyze(project, coverage="coverage.json"))
    assert found["add"].tested and found["add"].evidence == "coverage"
    assert not found["Cart.add"].tested
    assert "coverage" in analyze(project, coverage="coverage.json").mode


def test_complexity_counts_branches():
    import ast
    simple = ast.parse("def f(a):\n    return a\n").body[0]
    branchy = ast.parse("def f(a):\n    if a and a > 1:\n        return 1\n    for i in range(a):\n        pass\n").body[0]
    assert complexity_of(simple) == 1
    assert complexity_of(branchy) > complexity_of(simple)


def test_risk_grows_with_churn_and_complexity():
    from testgap.analyzer import Function
    calm = Function("a.py", "f", "f", 1, 5, complexity=1, churn=0)
    busy = Function("a.py", "g", "g", 1, 5, complexity=8, churn=12)
    assert risk_score(busy) > risk_score(calm)
    assert level(25) == "High" and level(12) == "Medium" and level(3) == "Low"


def test_missing_tests_folder_is_reported_as_warning(tmp_path):
    (tmp_path / "app.py").write_text("def run():\n    return 1\n")
    report = analyze(tmp_path)
    assert report.test_files == 0
    assert report.warnings and report.percent == 0.0


def test_module_names_for_imports():
    assert module_name("src/shop/cart.py", ["src"]) == "shop.cart"
    assert module_name("shop.py", ["."]) == "shop"
    assert module_name("src/pkg/__init__.py", ["src"]) == "pkg"


def test_skeleton_drafts_never_overwrite(project):
    report = analyze(project)
    out = project / "tests"
    written, skipped = write_drafts(report, out, limit=10)
    assert written and not skipped
    content = written[0].read_text()
    assert "import pytest" in content and "pytest.skip" in content
    again_written, again_skipped = write_drafts(report, out, limit=10)
    assert not again_written and again_skipped


def test_draft_limit_is_respected(project):
    report = analyze(project)
    written, _ = write_drafts(report, project / "drafts", limit=1)
    text = written[0].read_text()
    assert text.count("pytest.skip(") == 1


def test_renderers_produce_expected_content(project):
    report = analyze(project)
    assert "Untested functions" in render_text(report)
    assert "| Risk |" in render_markdown(report)
    data = json.loads(render_json(report))
    assert data["summary"]["functions"] == 4 and len(data["findings"]) == 4


def test_def_line_alone_does_not_count_as_covered(project):
    # Line 1 is "def add(a, b):" which runs on import, so it must not mark add() as tested.
    cov = {"files": {"src/calc.py": {"executed_lines": [1]}}}
    (project / "coverage.json").write_text(json.dumps(cov))
    found = _by_name(analyze(project, coverage="coverage.json"))
    assert not found["add"].tested


def test_load_coverage_handles_absolute_paths(project):
    cov = {"files": {str(project / "src" / "calc.py"): {"executed_lines": [2]}}}
    path = project / "cov.json"
    path.write_text(json.dumps(cov))
    assert load_coverage(path, project.resolve()) == {"src/calc.py": {2}}


def test_cli_scan_fail_under_returns_exit_code_1(project, capsys):
    assert main(["scan", "--root", str(project), "--fail-under", "100"]) == 1
    assert main(["scan", "--root", str(project), "--fail-under", "0"]) == 0


def test_cli_json_output_to_file(project):
    out = project / "report.json"
    assert main(["scan", "--root", str(project), "--format", "json", "-o", str(out)]) == 0
    assert json.loads(out.read_text())["summary"]["functions"] == 4


def test_cli_draft_creates_files(project):
    assert main(["draft", "--root", str(project), "--limit", "2"]) == 0
    assert len(list((project / "tests").glob("test_gaps_*.py"))) >= 1


def test_cli_reports_missing_folder(tmp_path, capsys):
    assert main(["scan", "--root", str(tmp_path / "nope")]) == 2


def test_demo_project_has_expected_gaps():
    report = analyze(DEMO)
    untested = {f.function.qualname for f in report.untested}
    assert {"calculate_total", "format_receipt", "Cart.remove_item", "Cart.total"} <= untested
    tested = {f.function.qualname for f in report.findings if f.tested}
    assert {"apply_discount", "Cart.add_item"} <= tested
