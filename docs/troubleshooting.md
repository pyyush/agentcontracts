# Troubleshooting

The Phase 1 audit found no open GitHub issues, so these are the top adoption questions from the audit, the runnable demos, and the release blockers fixed for `1.0.0`.

## 1. `aicontracts` is not on my PATH

Run the module form:

```bash
python -m agent_contracts.cli validate AGENT_CONTRACT.yaml
```

On macOS user installs, `pip` may put console scripts in a user bin directory that is not on `PATH`. A virtual environment avoids that:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
```

## 2. My file write is blocked even though the glob looks close

Filesystem authorization is repo-relative and canonicalized before matching. A pattern such as `src/**` authorizes `src/app.py`, not `tests/app.py`, `.env`, or traversal-shaped paths such as `src/../.env`. Add the narrowest real path you want the agent to edit.

## 3. My shell command is blocked

Shell commands are strict reject plus glob match. Any command containing `;`, `&`, `|`, `<`, `>`, backticks, `$(`, or a newline is denied before allowlist matching. If you need a pipeline or redirect, put it in a reviewed script and authorize the script command by name.

## 4. My `eval:` postcondition fails

`eval:` is an external evaluator hook, not a built-in LLM judge. In `1.0.0`, `sync_block` eval checks fail closed without an evaluator. Replace the check with a deterministic expression or wire a concrete evaluator in the host adapter.

## 5. `check-verdict` says the artifact schema is invalid

`check-verdict` validates `schemas/verdict.schema.json` before looking at the outcome. Ensure the artifact includes `run_id`, `contract`, `host`, `outcome`, `final_gate`, `violations`, `checks`, `budgets`, `artifacts`, `timestamp`, and `warnings`. Compare against the fixtures in `examples/verdicts/`.

## Debugging Downstream Runs

When a downstream repo reports a failure, ask for the exact `verdict.json`, not a screenshot or agent transcript. Start with `outcome`, `final_gate`, `violations[].violated_clause`, `checks[]`, `warnings[]`, and `budgets`. Then rerun:

```bash
python -m agent_contracts.cli check-verdict path/to/verdict.json --json-output
```

If the verdict is `blocked`, change the contract or the agent behavior. If it is `fail`, fix the required repo check or postcondition. If it is `warn`, decide whether the warning should stay non-blocking or become a required check before release.
