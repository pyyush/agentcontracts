# Runnable Examples

These examples are the release demo proof for `aicontracts 1.0.0`. Run them from the repo root after installing the package in editable mode:

```bash
python3 -m pip install -e ".[dev]"
python3 examples/run_green_pass.py
python3 examples/run_blocked_file_write.py
python3 examples/run_blocked_command.py
python3 examples/run_failed_checks.py
```

Each script writes a schema-valid verdict artifact under `examples/.demo-artifacts/` by default and prints a compact JSON summary.

| Script | Contract | Expected verdict | What it proves |
|---|---|---|---|
| `run_green_pass.py` | `repo_build_agent.yaml` | `pass` / `allowed` | A bounded repo run can record required checks and produce a green artifact. |
| `run_blocked_file_write.py` | `demo_blocked_file_write.yaml` | `blocked` / `blocked` | A write outside the allowed `filesystem.write` scope fails closed. |
| `run_blocked_command.py` | `demo_blocked_command.yaml` | `blocked` / `blocked` | A shell command with injection metacharacters fails closed before budget accounting. |
| `run_failed_checks.py` | `demo_failed_checks.yaml` | `fail` / `failed` | A run with red required checks cannot produce a passing verdict. |

Static sample artifacts live in `examples/verdicts/` for docs, PR review, and CI annotation examples. The test suite validates both the runnable scripts and the committed sample artifacts against `schemas/verdict.schema.json`.
