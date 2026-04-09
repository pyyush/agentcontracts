# agent-contracts

[![CI](https://github.com/pyyush/agentcontracts/actions/workflows/ci.yml/badge.svg)](https://github.com/pyyush/agentcontracts/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/aicontracts.svg)](https://pypi.org/project/aicontracts/)

**Declare what your coding agent may read, write, run, and spend — in one YAML file at the root of your repo. Enforced at runtime. Gated in CI. Fails closed.**

Works with Claude Code, Codex, Cursor, and any agent runtime — the core is framework- and provider-agnostic. Optional thin adapters for Claude Agent SDK, OpenAI Agents SDK, and LangChain.

```bash
pip install aicontracts
aicontracts init --template coding -o AGENT_CONTRACT.yaml
aicontracts validate AGENT_CONTRACT.yaml
```

> **The CI verdict gate is the source of truth.** Every run emits one durable `verdict.json`. The merge cannot go green if the verdict is `blocked` or `fail`. In-runtime adapters add convenience — the gate is what makes enforcement complete.

## Why this, why now

Coding agents are in production. Claude Code, Codex, Cursor Agent, Devin, Aider — every one of them runs with ambient authority over your repo: whatever the shell, filesystem, and network will let them do. The failure modes are no longer hypothetical:

- agents editing files outside the intended scope
- destructive shell commands run on the wrong branch
- silent token-budget overruns mid-loop
- the agent reports "all tests passing" while `pytest` on disk is red — and you merge it
- unauthorized network calls and tool use buried in the trace

A repo shouldn't trust an agent any more than it trusts a random PR. `agent-contracts` is the smallest thing that gives a repo a declarative *"here is exactly what this agent may do"* — and a CI gate that refuses to merge runs that violated it.

## What an agent cannot do under a contract

| Agent attempts | Without a contract | With agent-contracts |
|---|---|---|
| `Write(".env", ...)` | silently succeeds | not in `filesystem.write` → denied |
| `Bash("rm -rf node_modules")` | runs | not in `shell.commands` → denied |
| `Bash("python -m pytest tests/ ; rm -rf /")` | runs | shell metacharacter → denied |
| Fetches `https://evil.example.com` | runs | not in `network` → denied |
| Burns 200k tokens in a loop | silent | hits `max_tokens: 50000` → blocked |
| Reports "all tests passing" while pytest is red | merges green | postcondition fails → verdict: `fail`, CI gate red |

## Quick start

### 1. Generate a starter contract

```bash
aicontracts init --template coding -o AGENT_CONTRACT.yaml
```

This drops a ready-to-use coding-agent contract in your repo:

```yaml
agent_contract: "0.1.0"
identity:
  name: repo-build-agent
  version: "0.1.0"

effects:
  authorized:
    filesystem:
      read: ["src/**", "tests/**", "README.md", "pyproject.toml"]
      write: ["src/**", "tests/**", "README.md"]
    shell:
      commands:
        - "python -m pytest *"
        - "python -m ruff check *"
    tools: []
    network: []
    state_writes: []

resources:
  budgets:
    max_tokens: 50000
    max_tool_calls: 20
    max_shell_commands: 10
    max_duration_seconds: 1800

observability:
  run_artifact_path: ".agent-contracts/runs/{run_id}/verdict.json"

contract:
  postconditions:
    - name: repo_checks_green
      check: "checks.pytest.exit_code == 0 and checks.ruff.exit_code == 0"
```

Empty `tools`, `network`, and `state_writes` lists mean *default-deny*: the agent cannot use any tool, hit any network endpoint, or write to any tracked state unless you list it.

### 2. Hook it into your agent runtime

The Claude Agent SDK adapter forwards every tool call into the enforcer — no manual instrumentation:

```python
from agent_contracts import load_contract
from agent_contracts.adapters.claude_agent import ContractHooks
from claude_agent_sdk import ClaudeAgentOptions, query

contract = load_contract("AGENT_CONTRACT.yaml")
hooks = ContractHooks(contract)

options = ClaudeAgentOptions(hooks=hooks.get_hooks_config())
async for message in query(prompt="refactor src/app.py", options=options):
    if hasattr(message, "total_cost_usd"):
        hooks.track_result(message)

verdict = hooks.enforcer.finalize_run(output={"status": "done"})
print(verdict.outcome)  # pass | warn | blocked | fail
```

OpenAI Agents SDK and LangChain adapters follow the same pattern. For agents *without* an SDK hook surface (bash drivers, custom subprocess loops), the verdict gate in step 3 still catches every violation post-hoc.

### 3. Gate the verdict in CI

```bash
aicontracts validate AGENT_CONTRACT.yaml
aicontracts check-verdict .agent-contracts/runs/<run-id>/verdict.json
```

`check-verdict` exits non-zero on `blocked` or `fail`. Wire it into a required GitHub check and the merge cannot proceed without an honest contract pass.

## Verdict artifacts

Every meaningful run can emit one compact artifact, for example:

```json
{
  "run_id": "...",
  "outcome": "pass",
  "checks": [
    {"name": "pytest", "status": "pass", "exit_code": 0},
    {"name": "ruff", "status": "pass", "exit_code": 0}
  ],
  "budgets": {
    "tokens": 12345,
    "shell_commands": 2,
    "duration_seconds": 18.2
  },
  "violations": []
}
```

Outcome semantics:

- `pass` — required checks and blocking clauses passed
- `warn` — allowed to proceed, but warnings were recorded
- `blocked` — an operation was denied during the run
- `fail` — the run completed, but required checks or critical postconditions failed

## CLI

```bash
# Validate a contract and show coding/build surfaces
aicontracts validate AGENT_CONTRACT.yaml

# Generate a coding-agent starter template
aicontracts init --template coding -o AGENT_CONTRACT.yaml

# Bootstrap from traces
aicontracts init --from-trace traces.jsonl -o AGENT_CONTRACT.yaml

# Check composition compatibility
aicontracts check-compat producer.yaml consumer.yaml

# Gate a verdict artifact in CI (exits non-zero on blocked/fail)
aicontracts check-verdict .agent-contracts/runs/<run-id>/verdict.json
```

## Framework adapters (optional)

The core (contract, CLI, verdict artifact, GitHub Action) is framework-agnostic and provider-agnostic. Adapters are optional ergonomic helpers that wire in-runtime hook calls into the same enforcer. Each is pinned to a specific SDK version and tested against the real SDK in CI.

| Framework | Extra | Pinned SDK |
|---|---|---|
| Claude Agent SDK | `aicontracts[claude]` | `claude-agent-sdk==0.1.56` |
| OpenAI Agents SDK | `aicontracts[openai]` | `openai-agents==0.13.5` |
| LangChain | `aicontracts[langchain]` | `langchain-core==1.2.26` |

All three SDK extras require Python 3.10+. The core package supports Python 3.9+.

In-runtime adapters add hard-stop coverage where the host exposes a pre-execution hook, but enforcement completeness still depends on the host's hook surface. The CI verdict gate is what makes enforcement total: every merge runs the same evaluator against the same contract, regardless of which framework, model, or runtime produced the run.

### v0.3.0 roadmap

A companion `@aicontracts/*` TypeScript package with adapters for Vercel AI SDK, Claude TypeScript SDK, and OpenAI Agents JS is planned for v0.3.0.

## Shell command matching: threat model

Shell command authorization in v0.2.x is **strict reject + glob match**. Any command containing a shell metacharacter — `;` `&` `|` `<` `>` `` ` `` `$(` or a newline — is denied outright, even if its prefix matches an allowlisted pattern. This rules out command chaining, redirection, process substitution, and command injection at the contract layer.

```yaml
shell:
  commands:
    - "python -m pytest *"   # matches: python -m pytest tests/test_app.py
                              # denied:  python -m pytest tests/ ; rm -rf /
```

The trade-off: legitimate piped commands like `cat file | head` cannot be expressed as a single allowlist entry today. Wrap them in a script the contract authorizes by name, or split them into two records. v0.3.x will introduce a `shlex`-based token matcher that can express richer command shapes safely without weakening the fail-closed property.

## GitHub Action

```yaml
- uses: pyyush/agentcontracts@v0.2.0
  with:
    contract: AGENT_CONTRACT.yaml
    verdict: .agent-contracts/runs/${{ github.run_id }}/verdict.json
```

The action validates contracts and, when a verdict path is provided, fails the workflow for `blocked` or `fail` outcomes.

## Canonical examples

- `AGENT_CONTRACT.yaml` — canonical repo-build agent contract
- `examples/repo_build_agent.yaml` — reference coding/build repo contract
- `examples/demo_blocked_file_write.yaml` — protected-file demo
- `examples/demo_blocked_command.yaml` — forbidden-command demo
- `examples/demo_failed_checks.yaml` — red-checks demo
- `examples/support_triage.yaml` — broader tier-2 example retained for composition docs

## Project structure

```text
schemas/                          JSON Schema for AGENT_CONTRACT.yaml
spec/SPECIFICATION.md             Human-readable specification
src/agent_contracts/              Python SDK
  cli.py                          CLI entry point
  loader.py                       YAML loading + validation
  types.py                        Dataclasses / type model
  effects.py                      Tool, filesystem, network, and shell authorization
  budgets.py                      Budget tracking
  postconditions.py               Postcondition evaluation
  enforcer.py                     Runtime enforcement + verdict artifacts
  init_from_trace.py              Bootstrap from traces
  adapters/                       Host/framework integrations
examples/                         Reference contracts and demos
action.yml                        GitHub composite action
AGENT_CONTRACT.yaml               Canonical coding-agent contract
```

## Why YAML, not Markdown?

A contract is a machine-enforceable artifact, not documentation. Markdown is prose; YAML is structure. The difference matters when the same file has to be parsed by a CLI, an in-runtime enforcer, and a CI gate — and produce the same verdict every time.

- **Deterministic parse.** YAML has a JSON Schema (`schemas/agent-contract.schema.json`). Every runtime, in any language, produces the same parse tree from the same file. Markdown would require an LLM or a brittle regex extractor, and the verdict would depend on which extractor you used.
- **Fail-closed needs typed fields.** `effects.authorized.filesystem.write: ["src/**"]` is a list of glob patterns. There is no ambiguity about whether `tests/secret.env` is in scope. A Markdown bullet under "## Files the agent can write" is interpretation, and interpretation is exactly what coding-agent guardrails cannot afford.
- **Diff-friendly review.** YAML diffs per field. A reviewer can see "this PR added `python -m mypy *` to authorized shell commands" as a one-line change. Markdown prose diffs are noisy and merge conflicts on policy text are hard to reason about.
- **Versioned schema.** `agent_contract: "0.1.0"` declares the spec version. Older runtimes can refuse contracts they don't understand; newer runtimes can ignore unknown fields under the `x-` prefix. Markdown has no equivalent.
- **Cloud-native muscle memory.** kubectl, GitHub Actions, OpenAPI, Helm, GitLab CI, ArgoCD — every fail-closed policy artifact in the ecosystem is YAML or JSON. Engineers already know how to author, lint, and review it.
- **Still legible.** For the canonical coding-agent case (one identity block, one effects block, a few postconditions), the YAML is short enough to read without ceremony. The quick-start contract above fits on one screen.

Markdown is the right format for the *human spec* (`spec/SPECIFICATION.md`) and for prose explanations of how the system works. It is not the right format for the file the enforcer reads on every run.

## Scope and non-goals

This repo is intentionally narrow.

In scope:

- repo-local contracts for coding/build agents
- file, shell, tool, network, and budget boundaries
- runtime + CI gating
- durable verdict artifacts

Out of scope for the current release:

- hosted control planes
- compliance dashboards
- generic agent governance positioning
- speculative multi-agent infrastructure

## License

Apache-2.0
