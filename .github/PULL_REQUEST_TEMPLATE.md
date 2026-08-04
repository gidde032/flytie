## Summary

Brief description of what this PR does and why.

Fixes #<!-- issue number, if applicable -->

## Changes

- <!-- bullet list of changes -->

## Type of change

- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] New feature (non-breaking change that adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to change)
- [ ] Documentation update
- [ ] CI/CD or infrastructure change

## Testing

- [ ] All existing tests pass (`pytest`)
- [ ] Smoke tests pass (`pytest -m smoke`)
- [ ] New tests added for the change (if applicable)
- [ ] Quality gates pass (`ruff format --check && ruff check && mypy src`)

## Checklist

- [ ] CHANGELOG.md updated (if user-facing change)
- [ ] Documentation updated (if applicable — `docs/`, README, CONTRIBUTING)
- [ ] No new top-level imports of heavy dependencies (`weasyprint`, `anthropic`, `alembic`)
- [ ] `flytie --version` cold-start still under 600 ms

## Screenshots or output

If this changes CLI output or behavior, include before/after examples.
