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

The `[dev]` extra installs `pytest`, `ruff`, `mypy`, and `pre-commit`. The
`[pdf]` and `[ai]` extras pull in WeasyPrint (PDF export) and the Anthropic
SDK (AI suggestions). All three together is what `pip install -e ".[dev,pdf,ai]"`
gives you.

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
turning the PR red. See `ai-development-practices.md` §4 for the full
lesson behind this rule.

If you need to bypass either hook in a hurry (don't make a habit of it):

```bash
git commit --no-verify     # skip commit-stage hooks
git push --no-verify       # skip pre-push hook
```

## What CI runs

Two GitHub Actions workflows:

- `.github/workflows/ci.yml` — runs on every PR. Installs the dev extras,
  runs `ruff check`, `ruff format --check`, `mypy src`, and `pytest`. Same
  checks the pre-commit hooks run locally, plus `ruff format --check` as a
  belt-and-suspenders gate in case someone pushed without pre-commit
  installed.
- `.github/workflows/release.yml` — fires on `v*` tag pushes. Runs the
  same gates, then builds the sdist + wheel, asserts the tag matches
  `__version__` in `src/flytie/__init__.py`, and publishes to PyPI via
  Trusted Publishing (OIDC; no API token).

[pre-commit.ci](https://pre-commit.ci) is also enabled on the repo and
runs the commit-stage hooks on every PR. If you forgot to install
pre-commit locally and pushed unformatted code, pre-commit.ci will run
`ruff format` and push a follow-up commit fixing it. You'll get a
notification when this happens; just `git pull` to sync your branch.

## Running tests manually

```bash
pytest                       # full suite at your local terminal width
COLUMNS=80 pytest            # same as the pre-push hook (catches wrap fragility)
pytest -m smoke              # happy-path subset (v0.1.2: WIP — marker registered, no tests yet)
pytest tests/test_cli_*.py   # just the CLI tests
ruff check src tests         # lint
ruff format src tests        # format (or `ruff format --check` to verify only)
mypy src                     # type-check
```

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
- `ai-development-practices.md` (one folder up) — the living practices doc.
- `collaboration-retrospective.md` (one folder up) — narrative of the
  human-AI collaboration that produced flytie.

## Reporting issues

Open an issue at [github.com/finngidden/flytie/issues](https://github.com/finngidden/flytie/issues).
Include the output of `flytie info` and `flytie --version`, the command you
ran, the output you got, and what you expected to see. If the issue
involves the PDF or AI paths, mention which extras you have installed.
