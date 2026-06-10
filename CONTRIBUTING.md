# Contributing to flytie

Thanks for the interest! flytie is a small Python CLI, so the contribution
loop is short: clone, install in editable mode with the dev extras, install
the pre-commit hooks, and you're set.

## Local setup

```bash
git clone https://github.com/finngidden/flytie.git
cd flytie
pip install -e ".[dev,pdf,ai]"
pre-commit install --hook-type pre-commit --hook-type pre-push
```

The `[dev]` extra installs `pytest`, `ruff`, `mypy`, `pre-commit`,
`pdfminer.six` (used in tests to assert PDF content), and `syrupy`
(snapshot testing). The `[pdf]` and `[ai]` extras pull in WeasyPrint (PDF
export) and the Anthropic SDK (AI suggestions). All three together is what
`pip install -e ".[dev,pdf,ai]"` gives you.

WeasyPrint additionally needs native libraries (Pango, Cairo). See
[`README.md`](README.md#pdf-export-native-dependencies) for the OS install
commands. If you can't install those, skip the `[pdf]` extra — the PDF tests
will skip themselves cleanly, and `flytie export --html` works without them.

## What runs and when

The `.pre-commit-config.yaml` registers two stages of hooks:

| Stage     | When it fires    | What it does                                          |
|-----------|------------------|-------------------------------------------------------|
| commit    | every `git commit` | `ruff format` + `ruff check --fix` + basic hygiene  |
| pre-push  | every `git push`   | full `pytest` suite at `COLUMNS=80`                 |

**Commit-stage hooks are auto-fixing.** If `ruff format` rewrites a file,
the commit aborts so you can re-stage the formatted version and re-commit.
This is normal. The commit-stage hooks are sub-second to a few seconds.

**The pre-push hook runs the full pytest suite at a narrow terminal.**
This catches a specific class of bug where CLI output wraps at the column
boundary on CI but not locally, breaking substring assertions like
`assert "JSON parse error" in r.stdout` when Rich inserts a newline between
`JSON` and `parse`. Running at `COLUMNS=80` locally surfaces those failures
in ~40 seconds, which is much cheaper than letting CI catch them and
turning the PR red. See `ai-development-practices/assessment.md` §4 for
the full lesson behind this rule.

If you need to bypass either hook in a hurry (don't make a habit of it):

```bash
git commit --no-verify     # skip commit-stage hooks
git push --no-verify       # skip pre-push hook
```

## What CI runs

Two GitHub Actions workflows:

- `.github/workflows/ci.yml` — runs on every PR. Installs all extras
  (including the native Pango library so WeasyPrint loads), then runs
  `ruff format --check`, `ruff check`, `mypy src`, and `pytest --cov`
  with the 85% coverage floor. Same checks the pre-commit
  hooks run locally, plus the coverage gate. If your change drops total
  coverage under 85% CI fails with "FAIL Required test coverage of 85%
  not reached"; run `pytest --cov=src/flytie --cov-report=term-missing`
  locally to see exactly which lines/modules dropped, then add tests
  before pushing again.
- `.github/workflows/release.yml` — fires on `v*` tag pushes. Runs the
  same gates (across Python 3.10/3.11/3.12), then asserts the tag matches
  `__version__` in `src/flytie/__init__.py`, builds the sdist + wheel,
  and publishes to PyPI via Trusted Publishing (OIDC; no API token).

[pre-commit.ci](https://pre-commit.ci) is also enabled on the repo and
runs the commit-stage hooks on every PR. If you forgot to install
pre-commit locally and pushed unformatted code, pre-commit.ci will run
`ruff format` and push a follow-up commit fixing it. You'll get a
notification when this happens; just `git pull` to sync your branch.

### Note: `ci.yml`'s lint step is gate-only

The CI lint step runs `ruff format --check` and `ruff check` — no `--fix`.
Auto-fixing happens in two places that *aren't* the GitHub Actions runner:
in your local pre-commit hooks (which actually persist the fix back to your
working tree), and in pre-commit.ci (which pushes a follow-up commit to the
PR). Auto-fixing in `ci.yml` would only mutate the runner's ephemeral
filesystem and silently weaken the gate.

## Enabling pre-commit.ci (maintainer task)

If you fork the repo or move it elsewhere, pre-commit.ci needs to be
re-enabled on the new fork:

1. Visit https://github.com/apps/pre-commit-ci
2. Click "Configure" (or "Install" if you've never used it before)
3. Grant access to the relevant repo (or "all repositories" for blanket
   coverage of your future projects)

The `ci:` block at the bottom of `.pre-commit-config.yaml` already tells
pre-commit.ci which hooks to run, what to skip, and how often to auto-bump
hook versions — so once the app is installed there's no per-repo
configuration needed. The first PR after enrollment will show
`pre-commit-ci[bot]` activity in the checks list.

## Formatter policy

The project uses `ruff` for both linting and formatting. `ruff format`
produces Black-compatible output, so contributors who are used to Black
will see identical behavior; the older `black` dev dependency was dropped
in v0.1.2 to avoid running two formatters with the same opinions.

If you add a new third-party dependency to `pyproject.toml`, add it to
the `known-third-party` list under `[tool.ruff.lint.isort]` in the same
file. Without that entry, ruff's import-sorting heuristic can classify
the package differently on different machines (developer laptop vs. CI
runner), causing import-order thrashing between commits. The explicit
list was added in v0.1.2 to make classification deterministic.

## Running tests manually

```bash
pytest                       # full suite at your local terminal width
COLUMNS=80 pytest            # same as the pre-push hook (catches wrap fragility)
pytest -m smoke              # 5 happy-path tests, runs in ~3 s (quick local feedback)
pytest tests/test_cli_*.py   # just the CLI tests
ruff check src tests         # lint
ruff format src tests        # format (or `ruff format --check` to verify only)
mypy src                     # type-check
```

Note that `pre-commit run --all-files` runs **only** the commit-stage
hooks (`ruff format`, `ruff check --fix`, basic hygiene). The pre-push
hook (`COLUMNS=80 pytest`) is *not* run by `pre-commit run --all-files`
and must be invoked manually if you want a single "am I ready to push?"
command. The closest equivalent is `pre-commit run --all-files &&
COLUMNS=80 pytest`.

## Writing tests that exercise the CLI

The `tests/conftest.py` autouse fixture `_wide_cli_runner_env` patches
`CliRunner.invoke` to default `env={"COLUMNS": "200"}` for every test, so
you don't need to pass it yourself. Two equivalent patterns:

```python
# Pattern 1: inline construction (works because of the autouse patch)
def test_my_command(env_dirs):
    runner = CliRunner()
    result = runner.invoke(app, ["my-command"])
    assert result.exit_code == 0

# Pattern 2: fixture injection (preferred for new tests; more discoverable)
def test_my_command(env_dirs, cli_runner):
    result = cli_runner.invoke(app, ["my-command"])
    assert result.exit_code == 0
```

If you specifically want to assert against narrow-terminal behavior, pass
`env={"COLUMNS": "80"}` to the invoke call and the override wins.

## Project documentation

- [`fly-tying-tracker-spec.md`](fly-tying-tracker-spec.md) — the spec.
- [`docs/`](docs/index.md) — user-facing documentation (quickstart,
  command reference, etc.).
- [`CHANGELOG.md`](CHANGELOG.md) — release notes in Keep-a-Changelog format.

Internal-only docs (gitignored, kept locally for the project owner):

- `handoff.md` — agent-to-agent context-recovery doc.
- `phase-summaries/` — per-phase development write-ups.
- `ai-development-practices/` (directory at project root, split into per-topic files in v0.1.2) — the living practices doc; start at `index.md`.
- `collaboration-retrospective/` (directory at project root, split into per-topic files in v0.1.2) — narrative of the human-AI collaboration that produced flytie; start at `index.md`.

## Reporting issues

Open an issue at [github.com/finngidden/flytie/issues](https://github.com/finngidden/flytie/issues).
Include the output of `flytie info` and `flytie --version`, the command you
ran, the output you got, and what you expected to see. If the issue
involves the PDF or AI paths, mention which extras you have installed.
