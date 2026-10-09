# Test-Gap Finder

**Find the untested functions that matter most in a Python project, and draft starter tests for them.**

Most projects know their overall test coverage number, but that number does not say which gaps are dangerous. Test-Gap Finder ranks every untested function by risk, so you can fix the complicated, frequently changed code first.

For each function it tells you:

- whether any test exercises it,
- how complex it is (how many decision paths it has),
- how risky it is, combining complexity, size, and optionally how often its file changes in git,
- where it lives, so you can jump straight to it.

It can also create a test file for each of the riskiest gaps, either as a clearly marked skeleton or, if you choose, with an AI model drafting real tests for you to review.

---

## Contents

1. [Features](#features)
2. [Installation](#installation)
3. [Quick start](#quick-start)
4. [Commands and options](#commands-and-options)
5. [How risk is scored](#how-risk-is-scored)
6. [Two ways to detect tests](#two-ways-to-detect-tests)
7. [Drafting tests](#drafting-tests)
8. [Using it in continuous integration](#using-it-in-continuous-integration)
9. [Limitations](#limitations)
10. [Project structure](#project-structure)
11. [Running the tests](#running-the-tests)
12. [Troubleshooting](#troubleshooting)
13. [Privacy](#privacy)
14. [Extending the tool](#extending-the-tool)

---

## Features

- **Risk ranking** instead of a single percentage. The riskiest untested code appears first.
- **Two evidence modes.** A fast name-matching mode with no setup, and a stricter coverage mode that checks which lines actually ran.
- **Git-aware risk** (optional). Files that change often get a higher risk score.
- **Three output formats:** readable terminal text, Markdown for pull requests and wikis, and JSON for other tools.
- **CI gate.** `--fail-under 70` makes the build fail when too much of the code is untested.
- **Draft tests** written as skeletons, or drafted by Claude for you to review.
- **Safe by design.** It only reads your code. It never edits existing files, and it never runs your code.
- **Python 3.10+.** Works on macOS, Windows, and Linux.

---

## Installation

You need **Python 3.10 or newer**.

### macOS and Linux

```bash
cd test-gap-finder
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Windows (PowerShell)

```powershell
cd test-gap-finder
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

If PowerShell refuses to run the activation script, run this once: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

After installing, the `test-gap` command is available. You can also run it as `python -m testgap`.

**Optional:** to use AI-drafted tests, install the Claude extra with `pip install -e ".[claude]"` and set your API key (see [Drafting tests](#drafting-tests)).

---

## Quick start

Point the tool at any project that has a `tests` folder:

```bash
test-gap scan --root path/to/your/project
```

For the most accurate result, measure real coverage first (this takes one more step):

```bash
cd path/to/your/project
coverage run -m pytest
coverage json
test-gap scan --coverage coverage.json
```

To try it on the included demo project:

```bash
test-gap scan --root examples/demo_project
```

Output from the demo (name-matching mode, no coverage file):

```
Test-Gap Finder report for .../examples/demo_project

Functions analysed: 6
Tested: 2 (33.3%)
Untested: 4
Evidence used: test names
Test files found: 1
Git churn used: no

Untested functions, highest risk first:

  Risk  Level  Function                          Location                        Cx
  11.0  Medium calculate_total                   src/shop.py:12                   5
   6.3  Low    format_receipt                    src/shop.py:24                   3
   6.2  Low    Cart.remove_item                  src/shop.py:36                   3
   4.2  Low    Cart.total                        src/shop.py:39                   2

Cx = complexity (number of decision points plus one). Higher means more paths to test.
```

`calculate_total` is at the top: it has the most branches, and nothing tests it.

---

## Commands and options

### `test-gap scan`

Lists untested functions, highest risk first.

| Option | Meaning |
|---|---|
| `--root PATH` | Project folder (default: current folder) |
| `--source FOLDER` | Folder with the code to check, relative to `--root`. Repeat for several. Default: `src` if it exists, otherwise the whole project. |
| `--tests FOLDER` | Folder with test files (default: `tests`) |
| `--coverage FILE` | A `coverage.json` file to use for accurate evidence |
| `--churn` | Raise the risk of files changed often in git (last 180 days) |
| `--format text\|markdown\|json` | Output format (default: text) |
| `-o FILE` | Save the report to a file instead of printing it |
| `--top N` | Rows shown in text output (default: 25) |
| `--fail-under PERCENT` | Exit with code 1 if the tested percentage is below this value |

### `test-gap draft`

Writes starter test files for the riskiest untested functions.

| Option | Meaning |
|---|---|
| `--limit N` | How many functions to draft (default: 10, highest risk first) |
| `--out FOLDER` | Where to save the files (default: the tests folder) |
| `--with-claude` | Let Claude write real tests (needs an API key) |
| `--model NAME` | Model for `--with-claude` (default: `claude-sonnet-5-5`) |

All options from `scan` also work with `draft`.

**Exit codes:** `0` success, `1` the `--fail-under` threshold was not met, `2` a problem such as a missing folder.

---

## How risk is scored

```
risk = complexity x 2  +  lines / 10  +  git changes / 3 (capped at 10)
```

- **Complexity** counts decision points: `if`, `for`, `while`, `except`, conditional expressions, comprehension filters, and `and` / `or`. More paths means more ways to be wrong.
- **Lines** is the length of the function. Longer functions usually hide more behaviour.
- **Git changes** (only with `--churn`) counts commits that touched the file in the last 180 days. Code that changes often and has no tests is the most likely place for a future bug.

Levels: **High** at 20 or more, **Medium** at 10 or more, **Low** below 10.

Only public functions and methods are checked. Names starting with an underscore, including `__init__`, are skipped, because they are usually exercised through the public code that calls them.

---

## Two ways to detect tests

### 1. Name matching (default)

A function counts as tested if its name appears anywhere in a test file. This needs no setup, so it is a good first look.

Its weakness: names such as `run`, `get`, or `add` can appear in tests for unrelated code, so a gap can be hidden. Treat the result as an estimate.

### 2. Coverage data (recommended)

Coverage records which lines actually ran during the tests. A function counts as tested only if its body ran.

```bash
coverage run -m pytest
coverage json
test-gap scan --coverage coverage.json
```

Coverage mode is stricter and more accurate. The report says which evidence was used at the top.

---

## Drafting tests

### Skeleton mode (free, no network)

```bash
test-gap draft --limit 5
```

This creates one file per source file, such as `tests/test_gaps_src_shop.py`. Each function gets a test that is marked as skipped until you write the assertion:

```python
import pytest
from shop import Cart, calculate_total, format_receipt


def test_calculate_total_draft():
    """Check calculate_total (src/shop.py:12, complexity 5)."""
    pytest.skip("TODO: call calculate_total with real inputs and assert the result")
```

Replace each `skip` with a real call and an assertion, then run `pytest`. Skipped tests are shown in the output, so none of them can be forgotten silently.

### AI-drafted mode

```bash
export ANTHROPIC_API_KEY=your-key-here        # Windows PowerShell: $env:ANTHROPIC_API_KEY="your-key-here"
test-gap draft --with-claude --limit 5
```

Claude reads each function's source and writes two or three pytest tests for it. Every generated file is marked as AI-drafted at the top. **Read each test before you trust it.** The tool never runs the generated tests for you; run `pytest` yourself and check that each assertion is what you actually want.

### Safety rules for drafting

- Existing files are never overwritten. If `tests/test_gaps_src_shop.py` already exists, it is skipped and reported.
- Draft files are new, so you can keep, edit, or delete them freely.
- The generated code is not executed by test-gap.

---

## Using it in continuous integration

An example GitHub Actions workflow is in `examples/github-action.yml`. The core of it:

```yaml
- name: Run tests with coverage
  run: coverage run -m pytest && coverage json -o coverage.json

- name: Report untested functions
  run: test-gap scan --coverage coverage.json --format markdown -o test-gap-report.md --fail-under 70
```

The report becomes part of the job summary, and the build fails if less than 70% of the functions are tested. Adjust the threshold to suit your project, and raise it gradually as coverage improves rather than setting a high number on day one.

The same commands work in GitLab CI, Azure Pipelines, or any shell script.

---

## Limitations

- **Python only.** It reads Python with the standard `ast` module.
- **Name matching can be fooled.** Use coverage mode for decisions.
- **Complexity is an estimate.** It is a fast static approximation, not a full cyclomatic analysis.
- **Public functions only.** Private helpers are not listed, so a bug inside one may be hidden behind a tested public function.
- **It finds gaps, not bugs.** A tested function can still be wrong, and an untested function can be correct. Use the report to decide where to write tests first.
- **Drafted tests need review.** Skeletons assert nothing until you write the assertion, and AI drafts can be plausible but wrong.

---

## Project structure

```
test-gap-finder/
├── testgap/
│   ├── __init__.py       # version
│   ├── __main__.py       # allows: python -m testgap
│   ├── analyzer.py       # finds functions, scores risk, detects tests (name matching or coverage)
│   ├── cli.py            # the scan and draft commands
│   ├── drafter.py        # writes skeleton tests or AI-drafted tests
│   └── report.py         # text, Markdown and JSON output
├── examples/
│   ├── demo_project/     # a small project with deliberate gaps, for trying the tool
│   └── github-action.yml # CI example with a 70% threshold
├── tests/
│   └── test_testgap.py   # 18 offline tests for the tool itself
├── .env.example
├── .gitignore
├── pyproject.toml
├── requirements.txt
└── README.md
```

---

## Running the tests

```bash
pip install -e ".[dev]"
python -m pytest -q
```

The tests create temporary projects and do not call any API.

To check the demo project yourself:

```bash
cd examples/demo_project
python -m coverage run --source=src -m pytest
python -m coverage json -o coverage.json
test-gap scan --root . --coverage coverage.json
```

---

## Troubleshooting

| Problem | What to try |
|---|---|
| `test-gap: command not found` | Activate your environment, then run `pip install -e .` again |
| Every function is untested | Check `--tests` points at your test folder. The report warns when no test files are found. |
| `--with-claude needs ANTHROPIC_API_KEY` | Set the key in your environment, or add it to a `.env` file |
| `coverage.json` not found | Run `coverage json` after your tests, and pass the file with `--coverage` |
| Functions from the wrong folder appear | Set `--source` to your code folder, for example `--source app` |
| Drafted test cannot import my module | Make sure your source folder is importable, for example by adding it to `pythonpath` in `pytest.ini` or `pyproject.toml` |
| `Error: Project folder not found` | Check the path given to `--root` |

---

## Privacy

- `scan` and skeleton `draft` run entirely on your computer.
- `draft --with-claude` sends the source code of the functions being drafted to the Anthropic API. Use it only for code you are allowed to share with that service.
- Nothing is sent anywhere unless you use `--with-claude`.

---

## Extending the tool

- **Another language:** replace `parse_functions` in `testgap/analyzer.py` with a parser for that language. The rest of the tool works on the same data structure.
- **Other risk signals:** add a term to `risk_score` in `testgap/analyzer.py`, for example the number of callers, or a flag for security-sensitive names.
- **Other output formats:** add a renderer in `testgap/report.py`, such as HTML or CSV.

---

**Author:** Dr. Firend Alan Rasch · American University of Phnom Penh
**License:** MIT (or your preferred license)
