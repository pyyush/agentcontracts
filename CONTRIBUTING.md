# Contributing

Thanks for helping improve Agent Contracts. Keep changes narrow, evidence-backed,
and aligned with the repo-local contract model.

## Setup

```bash
python -m pip install -e ".[dev]"
```

For adapter work on Python 3.10 or newer:

```bash
python -m pip install -e ".[dev,claude,openai,langchain]"
```

## Canonical Checks

Run these before submitting a change:

```bash
python -m ruff check src/ tests/
python -m pytest --cov=agent_contracts --cov-report=term-missing
python -m mypy src/agent_contracts
python -m agent_contracts.cli validate AGENT_CONTRACT.yaml
python -m agent_contracts.cli validate examples/support_triage.yaml
python -m agent_contracts.cli check-compat examples/support_triage.yaml examples/support_triage.yaml
python -m pip_audit . --progress-spinner off
```

Adapter tests skip real-SDK checks when optional SDK packages are not installed.
Do not remove those skips unless CI has the matching extra installed.

## Release Hygiene

- Keep `1.0.0` wording truthful until both the PyPI package and `v1.0.0` GitHub tag exist.
- Update `CHANGELOG.md` for user-visible changes, security fixes, and migration notes.
- Keep generated files, local agent state, and internal planning files out of distributions.
- Use immutable action tags in user-facing examples after the package is published.

## Security

Use `SECURITY.md` for vulnerability reporting guidance. Do not paste secrets,
private repository content, or customer data into public issues or tests.
