# Agent Contracts Adoption Guide

This guide is for repo owners deciding whether `agent-contracts` is safe enough to put in front of coding agents.

## The Minimal Adoption Path

1. Add `AGENT_CONTRACT.yaml` to the repo.
2. Validate it locally with `python -m agent_contracts.cli validate AGENT_CONTRACT.yaml`.
3. Run or adapt one demo in `examples/` to produce a verdict artifact.
4. Gate the artifact in CI with `python -m agent_contracts.cli check-verdict <path>`.
5. Make the CI check required before merge.

The contract should start narrow. Authorize the files the agent is meant to touch, the commands it is meant to run, and the checks that prove the task is done. Expand the contract only after the first failed run explains a real missing permission.

## Host Integration Notes

### Claude Code

Use the repo contract and CI verdict gate as the source of truth. Current `agent-contracts` does not claim full pre-execution interception for every Claude Code native tool unless the host exposes the required hook payload. For local hard stops, route Claude Code work through a wrapper that calls `ContractEnforcer.check_file_read`, `check_file_write`, `check_shell_command`, and `check_network_request` before executing host actions. Always finalize a verdict and run `check-verdict` in CI.

### Codex

Use `AGENT_CONTRACT.yaml` plus CI gating for Codex sessions. If the Codex runner can expose attempted file, shell, tool, or network effects, forward them into `ContractEnforcer`. If not, record repo checks with `record_check(...)`, finalize the verdict, and rely on the required CI gate to reject blocked or failed runs. `aicontracts init --from-trace traces.jsonl` can bootstrap the first contract from observed Codex activity.

### Claude Agent SDK

Install `aicontracts[claude]` on Python 3.10+ and construct `agent_contracts.adapters.claude_agent.ContractHooks` from a loaded contract. The adapter can deny generic tools and common native effects before execution when the Claude hook payload includes the path, command, or URL. Call `hooks.finalize_run(...)` in a `finally` block so failed host runs still emit a verdict artifact.

### OpenAI Agents SDK

Install `aicontracts[openai]` on Python 3.10+ and use `agent_contracts.adapters.openai_agents.ContractRunHooks`. `on_tool_start` can deny generic tool names before tool execution, but the current OpenAI hook surface does not expose every file path, shell command, or URL. Treat the adapter as runtime coverage plus evidence, and keep `check-verdict` as the merge gate.

### LangChain

Install `aicontracts[langchain]` on Python 3.10+ and attach `agent_contracts.adapters.langchain.ContractCallbackHandler`. Conventional local wrappers such as `bash`, `read_file`, `write_file`, and `web_fetch` can be checked when their input strings contain the command, path, or URL. Call `handler.finalize_run(...)` when the chain raises before `on_chain_end`.

## CI And PR Review

A minimal GitHub Actions gate looks like this:

```yaml
- name: Validate agent contract
  run: python -m agent_contracts.cli validate AGENT_CONTRACT.yaml

- name: Gate agent verdict
  run: python -m agent_contracts.cli check-verdict .agent-contracts/runs/${{ github.run_id }}/verdict.json
```

For a friendlier PR summary, print the outcome, failed clauses, and check statuses into `$GITHUB_STEP_SUMMARY` after `check-verdict` fails:

```bash
python -m agent_contracts.cli check-verdict "$VERDICT" || {
  python - <<'PY' "$VERDICT" >> "$GITHUB_STEP_SUMMARY"
import json, sys
verdict = json.load(open(sys.argv[1], encoding="utf-8"))
print(f"## Agent contract verdict: {verdict['outcome']}")
for violation in verdict.get("violations", []):
    print(f"- `{violation['violated_clause']}`: `{violation.get('evidence', {})}`")
for check in verdict.get("checks", []):
    print(f"- check `{check['name']}`: `{check['status']}`")
PY
  exit 1
}
```

Reviewers should look for three things in the artifact:

- `outcome` and `final_gate` match the expected gate behavior.
- `violations[].violated_clause` points to a contract clause a human can fix or approve.
- Required checks cover the repo's real merge criteria, not only the agent's claim.

## Sample Artifacts

The `examples/verdicts/` directory contains committed sample artifacts for:

- a green pass
- a blocked file write
- a blocked shell command
- failed repo checks

All samples validate against `schemas/verdict.schema.json` and are safe fixtures for docs, CI summaries, and PR review tooling.
