## Summary

- 

## Verification

- [ ] `python -m ruff check src/ tests/`
- [ ] `python -m pytest --cov=agent_contracts --cov-report=term-missing`
- [ ] `python -m mypy src/agent_contracts`
- [ ] `python -m agent_contracts.cli validate AGENT_CONTRACT.yaml`
- [ ] `python -m agent_contracts.cli validate examples/support_triage.yaml`
- [ ] `python -m agent_contracts.cli check-compat examples/support_triage.yaml examples/support_triage.yaml`
- [ ] `python -m pip_audit . --progress-spinner off`

## Release Impact

- [ ] No user-visible change
- [ ] Changelog updated
- [ ] Migration notes updated
- [ ] Security notes updated
