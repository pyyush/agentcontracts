# agent-contracts

[![CI](https://github.com/pyyush/agentcontracts/actions/workflows/ci.yml/badge.svg)](https://github.com/pyyush/agentcontracts/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/aicontracts.svg)](https://pypi.org/project/aicontracts/)

**Declare what your coding agent may read, write, run, and spend — in one YAML file at the root of your repo. Enforced at runtime. Gated in CI. Fails closed.**

Works with Claude Code, Codex, Cursor, and any agent runtime — the core is framework- and provider-agnostic. Optional thin adapters for Claude Agent SDK, OpenAI Agents SDK, and LangChain.

> **Release status:** This branch is preparing `aicontracts 1.0.0` and contract spec `1.0.0`. PyPI currently publishes `aicontracts 0.2.0`; do not treat `1.0.0` as available until the PyPI package and `v1.0.0` GitHub tag are both published.

Published install:

```bash
pip install aicontracts
aicontracts init --template coding -o AGENT_CONTRACT.yaml
aicontracts validate AGENT_CONTRACT.yaml
```

Release-branch install to first working example, under five minutes:

```bash
git clone https://github.com/pyyush/agentcontracts.git
cd agentcontracts
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
python -m agent_contracts.cli validate AGENT_CONTRACT.yaml
python examples/run_green_pass.py
python -m agent_contracts.cli check-verdict examples/.demo-artifacts/green-pass.json
```

Expected result: the demo prints `outcome: pass`, writes a schema-valid verdict artifact, and `check-verdict` exits zero. The blocked and failed demos in `examples/` show the two red-path gates.

> **The CI verdict gate is the source of truth.** Every run emits one durable `verdict.json`. The merge cannot go green if the verdict is `blocked` or `fail`. In-runtime adapters add convenience — the gate is what makes enforcement complete.

## Why this, why now

Coding agents are in production. Claude Code, Codex, Cursor Agent, Devin, Aider — every one of them runs with ambient authority over your repo: whatever the shell, filesystem, and network will let them do. The failure modes are no longer hypothetical:

- agents editing files outside the intended scope
- destructive shell commands run on the wrong branch
- silent token-budget overruns mid-loop
- the agent reports "all tests passing" while `pytest` on disk is red — and you merge it
- unauthorized network calls and tool use buried in the trace

A repo shouldn't trust an agent any more than it trusts a random PR. `agent-contracts` is the smallest thing that gives a repo a declarative *"here is exactly what this agent may do"* — and a CI gate that refuses to merge runs that violated it.

## Top 3 adoption questions

**Why use this instead of prompt instructions?** Prompt instructions are advisory. `AGENT_CONTRACT.yaml` is parsed, enforced by the runtime where hooks exist, and checked again in CI from a durable verdict artifact.

**What if my agent host cannot expose every native file or shell action?** Use the adapter for the coverage the host exposes, then make `aicontracts check-verdict` a required CI gate. The final verdict can still reject red repo checks and malformed or blocked artifacts even when the local host is only partially observable.

**How much work is first adoption?** Start with `aicontracts init --template coding`, narrow file and shell scopes, run one example from `examples/`, and add the GitHub Action or `check-verdict` command to CI. The release-branch quick start above proves the loop without any hosted service.

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
agent_contract: "1.0.0"
identity:
  name: repo-build-agent
  version: "1.0.0"

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

When `effects.authorized` is present, every effect sub-surface is fail-closed. Empty `tools`, `network`, and `state_writes` lists mean the agent cannot use any tool, hit any network endpoint, or write to tracked state unless you list it. Omitted or empty `filesystem` and `shell` sub-surfaces deny file and shell effects by default. Leaving `effects.authorized` out entirely is the explicit unconfigured mode for compatibility and does not enforce effect gates.

Postconditions are deterministic by default. `eval:*` checks are external evaluator hooks, not built-in LLM judges; without an evaluator integration, `sync_block` eval checks fail closed and `sync_warn` or `async_monitor` eval checks emit visible warnings instead of passing.

### 2. Hook it into your agent runtime

The Claude Agent SDK adapter forwards observable tool calls into the enforcer and provides an explicit verdict finalizer:

```python
from agent_contracts import load_contract
from agent_contracts.adapters.claude_agent import ContractHooks
from claude_agent_sdk import ClaudeAgentOptions, query

contract = load_contract("AGENT_CONTRACT.yaml")
hooks = ContractHooks(contract)

options = ClaudeAgentOptions(hooks=hooks.get_hooks_config())
error = None
try:
    async for message in query(prompt="refactor src/app.py", options=options):
        if hasattr(message, "total_cost_usd"):
            hooks.track_result(message)
except Exception as exc:
    error = exc
    raise
finally:
    verdict = hooks.finalize_run(output={"status": "done"}, execution_error=error)
print(verdict.outcome)  # pass | warn | blocked | fail
```

OpenAI Agents SDK and LangChain adapters follow the same pattern. For agents *without* an SDK hook surface (bash drivers, custom subprocess loops), the verdict gate in step 3 still catches every violation post-hoc.

### 3. Gate the verdict in CI

```bash
aicontracts validate AGENT_CONTRACT.yaml
aicontracts check-verdict .agent-contracts/runs/<run-id>/verdict.json
```

`check-verdict` validates the verdict schema first, then exits non-zero on `blocked` or `fail`. Wire it into a required GitHub check and the merge cannot proceed without an honest contract pass.

## Verdict artifacts

Every meaningful governed run should be finalized with one schema-backed artifact. The public schema lives at `schemas/verdict.schema.json`, with the packaged runtime copy at `src/agent_contracts/schemas/verdict.schema.json`.

```json
{
  "run_id": "...",
  "contract": {
    "name": "repo-build-agent",
    "version": "1.0.0",
    "spec_version": "1.0.0"
  },
  "host": {
    "name": "claude-agent-sdk",
    "version": "0.1.56"
  },
  "outcome": "pass",
  "final_gate": "allowed",
  "violations": [],
  "checks": [
    {"name": "pytest", "status": "pass", "required": true, "exit_code": 0},
    {"name": "ruff", "status": "pass", "required": true, "exit_code": 0}
  ],
  "budgets": {
    "cost_usd": 0.0,
    "tokens": 12345,
    "tool_calls": 6,
    "shell_commands": 2,
    "duration_seconds": 18.2
  },
  "artifacts": {
    "verdict_path": ".agent-contracts/runs/<run-id>/verdict.json",
    "contract_path": "AGENT_CONTRACT.yaml"
  },
  "timestamp": "2026-05-04T00:00:00+00:00",
  "warnings": []
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

## API reference

The stable public Python imports for the `1.0.0` release train are documented in the generated API reference at `docs/api-reference.md`. Regenerate it with:

```bash
python scripts/generate_api_reference.py
python scripts/generate_api_reference.py --check
```

Hosted path after merge: https://github.com/pyyush/agentcontracts/blob/main/docs/api-reference.md.

## Version policy

`aicontracts` package versions and `agent_contract` spec versions are related but distinct SemVer streams. For the planned stable release, package `1.0.0` implements contract spec `1.0.0` and the stable verdict artifact schema. After that, package patch and minor releases may continue to implement contract spec `1.0.0`; the spec version changes only when the YAML contract or verdict artifact semantics change.

New stable contracts should declare `agent_contract: "1.0.0"`. `identity.version` is the version of the agent described by the contract, so it can differ from both the package version and the spec version.

SemVer stability covers:

- **Python API:** public imports from `agent_contracts`, typed contract objects, exceptions, and verdict helpers.
- **CLI:** command names, option names, exit-code semantics, and JSON output shapes.
- **Contract schema:** required fields, allowed field meanings, and fail-closed authorization semantics.
- **Verdict schema:** required artifact fields, outcome/final-gate semantics, and `check-verdict` gating behavior.
- **GitHub Action:** input names, output names, outcome behavior, and the package pin installed by each release tag.

Major releases may make incompatible changes to those surfaces. Minor releases add backward-compatible capabilities. Patch releases fix bugs, security issues, and documentation without changing stable semantics.

Migration notes from `0.2.0` to `1.0.0` live in `docs/migration-0.2-to-1.0.md`.

## Performance guardrails

The `1.0.0` release tracks concrete budgets for the hot paths that decide
whether a governed run can finish: effect authorization, postcondition
evaluation, and trace-to-contract bootstrap. The baseline artifact lives at
`benchmarks/performance-baselines.json`, the release notes for the budgets
live in `benchmarks/README.md`, and the budgets are enforced by
`tests/test_performance_baselines.py` as part of the standard pytest suite.

Current release budgets are intentionally conservative: 10,000 mixed effect
checks must complete within 1.5 seconds, 1,000 postconditions within 300 ms,
and bootstrapping 2,500 JSONL traces within 750 ms. Tightening or loosening
those budgets is a release-plan decision, not an incidental test edit.

## Framework adapters (optional)

The core (contract, CLI, verdict artifact, GitHub Action) is framework-agnostic and provider-agnostic. Adapters are optional ergonomic helpers that wire in-runtime hook calls into the same enforcer. Each is pinned to a specific SDK version and tested against the real SDK in CI.

| Framework | Extra | Pinned SDK |
|---|---|---|
| Claude Agent SDK | `aicontracts[claude]` | `claude-agent-sdk==0.1.56` |
| OpenAI Agents SDK | `aicontracts[openai]` | `openai-agents==0.13.5` |
| LangChain | `aicontracts[langchain]` | `langchain-core==1.2.28` |

All three SDK extras require Python 3.10+. The core package supports Python 3.9+.

In-runtime adapters add hard-stop coverage where the host exposes a pre-execution hook, but enforcement completeness still depends on the host's hook surface. The CI verdict gate is what makes enforcement total: every merge runs the same evaluator against the same contract, regardless of which framework, model, or runtime produced the run.

### Adapter verdict behavior

All adapters expose `finalize_run(...)`, return a schema-backed `RunVerdict`, and write the verdict artifact through the same enforcer used by the CLI gate. If finalization happens before the adapter sees host completion, or completion is observed without any output or execution error, the verdict records a required adapter check failure instead of passing silently.

| Adapter | Run start | Pre-execution checks | Finalization |
|---|---|---|---|
| Claude Agent SDK | `ContractHooks` allocates the run id when constructed; the SDK does not expose a separate run-end hook here. | `PreToolUse` can deny generic tools and common inspectable native effects before execution: `Read`, `Write`, `Edit`, `MultiEdit`, `NotebookEdit`, `Bash`, and `WebFetch` when the hook payload contains the path, command, or URL. | Call `hooks.finalize_run(...)` after the query loop, preferably in `finally`. `track_result(...)` records cost/token usage and marks host completion observed, but does not finalize by itself. |
| OpenAI Agents SDK | `ContractRunHooks` allocates the run id when constructed; `on_agent_start` marks host execution observed. | `on_tool_start` can deny generic tool names before tool execution, but after the model has already chosen the tool. This hook surface does not expose file paths, shell commands, or URLs, so native effect arguments are not checkable here. | `on_agent_end` validates output, evaluates postconditions, and finalizes. Surrounding code should call `hooks.finalize_run(execution_error=exc)` when the host raises before `on_agent_end`. |
| LangChain | `ContractCallbackHandler` allocates the run id when constructed. | `on_tool_start` can deny generic tool names and conventional local wrappers such as `bash`, `read_file`, `write_file`, and `web_fetch` when the input string contains the command, path, or URL. | `on_chain_end` validates output, evaluates postconditions, and finalizes. Surrounding code should call `handler.finalize_run(execution_error=exc)` when the chain raises before `on_chain_end`. |

OpenAI and LangChain strict mode raises `AdapterVerdictError` when their completion callback finalizes to `blocked` or `fail`. Claude pre-tool denials return the SDK's structured deny response; the final verdict still becomes `blocked` when finalized. Unsupported or unobserved effects must be caught by repo checks and `check-verdict` in CI.

### Post-1.0 roadmap

A companion `@aicontracts/*` TypeScript package with adapters for Vercel AI SDK, Claude TypeScript SDK, and OpenAI Agents JS is planned after the stable Python release.

## Shell command matching: threat model

Shell command authorization is **strict reject + glob match**. Any command containing a shell metacharacter — `;` `&` `|` `<` `>` `` ` `` `$(` or a newline — is denied outright, even if its prefix matches an allowlisted pattern. This rules out command chaining, redirection, process substitution, and command injection at the contract layer.

```yaml
shell:
  commands:
    - "python -m pytest *"   # matches: python -m pytest tests/test_app.py
                              # denied:  python -m pytest tests/ ; rm -rf /
```

The trade-off: legitimate piped commands like `cat file | head` cannot be expressed as a single allowlist entry today. Wrap them in a script the contract authorizes by name, or split them into two records. A future minor release may introduce a `shlex`-based token matcher that can express richer command shapes safely without weakening the fail-closed property.

## GitHub Action

```yaml
- uses: pyyush/agentcontracts@v1.0.0
  with:
    contract: AGENT_CONTRACT.yaml
    verdict: .agent-contracts/runs/${{ github.run_id }}/verdict.json
```

Use immutable release tags for production workflows. The planned `v1.0.0` action tag installs `aicontracts==1.0.0`, so the GitHub tag must not be cut until the PyPI package is published. Before that release exists, keep production workflows pinned to the latest published 0.x action tag.

For release-candidate validation only, keep the action ref pinned to the RC tag
and override `package-spec` so the action installs the exact RC package being
validated:

```yaml
- uses: pyyush/agentcontracts@<RC_TAG>
  with:
    contract: AGENT_CONTRACT.yaml
    verdict: .agent-contracts/runs/${{ github.run_id }}/verdict.json
    package-spec: "<RC_WHEEL_URL_OR_aicontracts==1.0.0rc1>"
    allow-prerelease: "true"
```

Production workflows should not override `package-spec` after `v1.0.0` exists;
the default remains the stable final `aicontracts==1.0.0` pin.

The action validates contracts and, when a verdict path is provided, schema-validates the artifact before failing the workflow for `blocked` or `fail` outcomes.

For PR review, prefer showing the verdict outcome, failed clauses, and required check statuses in the workflow summary. `docs/adoption-guide.md` includes a copy-paste summary snippet and host-specific notes for Claude Code, Codex, Claude Agent SDK, OpenAI Agents SDK, and LangChain.

## Debugging downstream failures

When a downstream user reports a failed or blocked run, ask for the exact `verdict.json`. The useful fields are `outcome`, `final_gate`, `violations[].violated_clause`, `violations[].evidence`, `checks[]`, `warnings[]`, and `budgets`. Re-run `python -m agent_contracts.cli check-verdict path/to/verdict.json --json-output` locally before changing code; a `blocked` verdict usually means the contract or agent behavior needs narrowing, while a `fail` verdict means a required repo check or postcondition is red.

## Canonical examples

- `AGENT_CONTRACT.yaml` — canonical repo-build agent contract
- `examples/repo_build_agent.yaml` — reference coding/build repo contract
- `examples/demo_blocked_file_write.yaml` — protected-file demo
- `examples/demo_blocked_command.yaml` — forbidden-command demo
- `examples/demo_failed_checks.yaml` — red-checks demo
- `examples/run_green_pass.py` — runnable green verdict demo
- `examples/run_blocked_file_write.py` — runnable blocked file-write verdict demo
- `examples/run_blocked_command.py` — runnable blocked shell verdict demo
- `examples/run_failed_checks.py` — runnable failed-check verdict demo
- `examples/verdicts/*.json` — schema-valid sample verdict artifacts for docs and PR summaries
- `examples/support_triage.yaml` — broader tier-2 example retained for composition docs

Troubleshooting for the top adoption questions lives in `docs/troubleshooting.md`.

## Project structure

```text
schemas/                          JSON Schemas for AGENT_CONTRACT.yaml and verdict artifacts
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
- **Versioned schema.** `agent_contract: "1.0.0"` declares the spec version. Older runtimes can refuse contracts they don't understand; newer runtimes can ignore unknown fields under the `x-` prefix. Markdown has no equivalent.
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
