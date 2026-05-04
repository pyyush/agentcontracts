# Agent Contracts 1.0 Release Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `agent-contracts` as a stable, secure, valuable major release for repo-local fail-closed coding/build-agent guardrails.

**Architecture:** Keep the project narrow: one repo-local YAML contract, one Python enforcement library, one CLI, one verdict artifact, one GitHub Action gate, and thin host adapters. The release sequence fixes security and fake-green failure modes first, then freezes public schemas/semantics, then hardens adapters, CI, docs, and release hygiene.

**Tech Stack:** Python 3.9+ core package, Click CLI, PyYAML, jsonschema, pytest/coverage, ruff, mypy, pip-audit, GitHub Actions composite action, optional Claude/OpenAI/LangChain SDK adapters.

---

## Target Version

Target release: `1.0.0`.

Semver justification:

- The current published package is `aicontracts 0.2.0` and is classified Alpha.
- The mission is a stable major release with semver-stable public API, CLI behavior, contract schema, verdict schema, adapter semantics, and action behavior.
- The required work changes or freezes user-facing semantics: fail-closed missing effect sub-surfaces, filesystem path authorization, `eval:` postconditions, verdict artifact validation, spec/package version policy, and adapter finalization. Those are major-release contract decisions.
- If users need an urgent security patch before the major train completes, cut `0.2.1` for the vulnerable LangChain pin and filesystem traversal fix, but this plan's release target remains `1.0.0`.

## Cycle Estimate Key

One cycle means one focused implementation pass with tests and local verification by one engineer/agent, typically a half day to one day depending on review depth. Estimates include implementation, tests, and direct docs for the task, but not RC soak time.

## Release Workstreams

### Task 1: Patch Dependency Vulnerability

**DoD:** Security, Release & distribution, Tests

**Status:** Complete in Phase 3 Task 1.

**Estimate:** 1 cycle

**Dependencies:** None

**Files likely touched in Phase 3:**

- `pyproject.toml`
- `README.md`
- `CHANGELOG.md`
- `.github/workflows/ci.yml`
- tests under `tests/test_adapters/`

**Plan:**

- [x] Replace or remove the vulnerable `langchain-core==1.2.26` optional pin.
- [x] Prefer a fixed compatible version if adapter tests pass; audit noted fixed versions `1.2.28` or `0.3.84`.
- [x] Verify current PyPI availability before editing.
- [x] Run adapter tests for LangChain on Python 3.10+.
- [x] Run `pip-audit` against core plus optional extras.

**Acceptance:**

- `pip-audit` reports no known vulnerabilities for core and extras.
- LangChain adapter tests pass against the selected pin.
- README optional-extra table and changelog match the shipped pin.

**Risks/blockers:**

- Newer LangChain may break callback API compatibility.
- If fixed LangChain versions are incompatible, temporarily remove or mark the LangChain extra unsupported until an adapter-compatible fixed version is found.

### Task 2: Fix Filesystem Path Canonicalization

**DoD:** Security, Stability, Tests, API quality

**Status:** Complete in Phase 3 Task 2.

**Estimate:** 2 cycles

**Dependencies:** None

**Files likely touched in Phase 3:**

- `src/agent_contracts/effects.py`
- `src/agent_contracts/enforcer.py`
- `tests/test_effects.py`
- `tests/test_enforcer.py`
- `spec/SPECIFICATION.md`

**Plan:**

- [x] Make filesystem authorization compare only canonical repo-relative paths plus clearly documented absolute paths inside the repo.
- [x] Reject or deny paths that resolve outside the repo root.
- [x] Add regression tests for `src/../.env`, absolute outside paths, symlink-like traversal cases where feasible, and normal allowed repo paths.
- [x] Keep glob semantics stable for legitimate `src/**`, `tests/**`, and exact-file patterns.

**Acceptance:**

- `src/../.env` does not match `src/**`.
- Paths outside the repo root are denied when filesystem authorization is configured.
- Existing canonical examples still validate and pass smoke tests.

**Verification:** Completed for Phase 3 Task 2.

- `python3 -m ruff check src/ tests/`: passed.
- `python3 -m pytest --cov=agent_contracts --cov-report=term-missing`: passed, 193 passed, 6 skipped, 91% coverage.
- `python3 -m mypy src/agent_contracts`: passed.
- CLI smoke checks for `AGENT_CONTRACT.yaml`, `examples/support_triage.yaml`, and `check-compat examples/support_triage.yaml examples/support_triage.yaml`: passed.
- Core `pip-audit`: no known vulnerabilities found.
- Optional extras `pip-audit` with `langchain-core==1.2.28`, `openai-agents==0.13.5`, and `claude-agent-sdk==0.1.56`: no known vulnerabilities found.

**Risks/blockers:**

- Existing users may rely on raw-pattern matching for unusual paths. Document this as a security hardening change for `1.0.0`.

### Task 3: Enforce Fail-Closed Missing Effect Sub-Surfaces

**DoD:** Value, Security, Stability, API quality, Docs, Tests

**Status:** Complete in Phase 3 Task 3.

**Estimate:** 2 cycles

**Dependencies:** Task 2 should land first so filesystem behavior is safe before tightening defaults.

**Files likely touched in Phase 3:**

- `src/agent_contracts/effects.py`
- `src/agent_contracts/enforcer.py`
- `src/agent_contracts/types.py`
- `src/agent_contracts/loader.py`
- `schemas/agent-contract.schema.json`
- `src/agent_contracts/schemas/agent-contract.schema.json`
- `tests/test_effects.py`
- `tests/test_loader.py`
- `tests/test_enforcer.py`
- `README.md`
- `spec/SPECIFICATION.md`
- examples under `examples/`

**Plan:**

- [x] Define `1.0.0` coding/build mode semantics: when `effects.authorized` is present, absent `tools`, `network`, `state_writes`, `filesystem`, and `shell` sub-surfaces are deny-by-default for their effect type.
- [x] Preserve backward compatibility only through explicit migration docs, not by keeping unsafe default-allow behavior.
- [x] Add tests that omit `filesystem` and `shell` and prove file/shell checks are denied.
- [x] Update examples to include intentional empty sub-surfaces where the user means "deny all".

**Acceptance:**

- Missing `filesystem` no longer allows arbitrary file reads/writes when effects authorization is configured.
- Missing `shell` no longer allows arbitrary shell commands when effects authorization is configured.
- Docs clearly distinguish "authorization absent entirely" from "authorization configured and sub-surface omitted".

**Verification:** Completed for Phase 3 Task 3.

- `python3 -m ruff check src/ tests/`: passed.
- `python3 -m pytest --cov=agent_contracts --cov-report=term-missing`: passed, 197 passed, 6 skipped, 91% coverage.
- `python3 -m mypy src/agent_contracts`: passed.
- CLI smoke checks for `AGENT_CONTRACT.yaml`, `examples/support_triage.yaml`, and `check-compat examples/support_triage.yaml examples/support_triage.yaml`: passed.
- Core `pip-audit`: no known vulnerabilities found.
- Optional extras `pip-audit` with `langchain-core==1.2.28`, `openai-agents==0.13.5`, and `claude-agent-sdk==0.1.56`: no known vulnerabilities found.

**Risks/blockers:**

- This is a breaking semantic change for pre-1.0 users. It is acceptable for `1.0.0`, but must be prominent in migration notes.

### Task 4: Eliminate `eval:` Fake-Green Postconditions

**DoD:** Value, Stability, Security, API quality, Docs, Tests

**Estimate:** 2 cycles

**Status:** Complete

**Dependencies:** None

**Files likely touched in Phase 3:**

- `src/agent_contracts/postconditions.py`
- `src/agent_contracts/enforcer.py`
- `src/agent_contracts/types.py`
- `schemas/agent-contract.schema.json`
- `src/agent_contracts/schemas/agent-contract.schema.json`
- `tests/test_postconditions.py`
- `tests/test_enforcer.py`
- `README.md`
- `spec/SPECIFICATION.md`
- `CHANGELOG.md`

**Plan:**

- [x] Replace automatic pass behavior for `eval:` checks with explicit unsupported, skipped, or adapter-required semantics.
- [x] Prefer fail-closed for `sync_block` `eval:` postconditions unless a concrete evaluator callback is supplied.
- [x] Add tests for `sync_block`, `sync_warn`, and `async_monitor` `eval:` checks.
- [x] Document the exact behavior and how future judge integrations should plug in.

**Acceptance:**

- A blocking `eval:` postcondition cannot produce a passing verdict without an evaluator.
- Warnings and skipped states are visible in verdict artifacts where applicable.
- README no longer implies LLM-as-judge checks work without integration.

**Verification:**

- `python3 -m ruff check src/ tests/`: passed.
- `python3 -m pytest --cov=agent_contracts --cov-report=term-missing`: passed, 203 passed, 6 skipped, 91% coverage.
- `python3 -m mypy src/agent_contracts`: passed.
- CLI smoke checks for `AGENT_CONTRACT.yaml`, `examples/support_triage.yaml`, and `check-compat examples/support_triage.yaml examples/support_triage.yaml`: passed.
- Core `pip-audit`: no known vulnerabilities found.
- Optional extras `pip-audit` with `langchain-core==1.2.28`, `openai-agents==0.13.5`, and `claude-agent-sdk==0.1.56`: no known vulnerabilities found.

**Risks/blockers:**

- This is a breaking semantic change for any pre-1.0 contract that relied on placeholder `eval:` checks passing. It must remain prominent in migration notes.

### Task 5: Add Verdict Artifact Schema Validation

**DoD:** API quality, Stability, Security, Observability, Tests, Release & distribution

**Status:** Complete (2026-05-04)

**Estimate:** 2 cycles

**Dependencies:** Task 4 should land first if verdict semantics change for `eval:` checks.

**Files likely touched in Phase 3:**

- `schemas/verdict.schema.json`
- `src/agent_contracts/schemas/verdict.schema.json`
- `src/agent_contracts/schema.py`
- `src/agent_contracts/enforcer.py`
- `src/agent_contracts/cli.py`
- `tests/test_enforcer.py`
- `tests/test_cli.py`
- `README.md`
- `spec/SPECIFICATION.md`

**Plan:**

- [x] Define a JSON Schema for verdict artifacts including `run_id`, `contract`, `host`, `outcome`, `final_gate`, `violations`, `checks`, `budgets`, `artifacts`, `timestamp`, and `warnings`.
- [x] Validate generated verdicts in tests.
- [x] Make `check-verdict` validate schema before evaluating outcome.
- [x] Add fixture tests for malformed JSON, missing fields, invalid outcomes, blocked/fail/warn/pass outcomes.

**Acceptance:**

- `check-verdict` rejects malformed verdict artifacts with clear errors.
- Generated `RunVerdict.to_dict()` output validates against the schema.
- CI/action docs point to the schema-backed verdict contract.

**Verification:**

- Completed for Phase 3 Task 5.
- `python3 -m ruff check src/ tests/`: passed.
- `python3 -m pytest --cov=agent_contracts --cov-report=term-missing`: passed, 211 passed, 6 skipped, 91% coverage.
- `python3 -m mypy src/agent_contracts`: passed.
- CLI smoke checks passed: `validate AGENT_CONTRACT.yaml`, `validate examples/support_triage.yaml`, and `check-compat examples/support_triage.yaml examples/support_triage.yaml`.
- Core `pip-audit`: no known vulnerabilities.
- Optional extras `pip-audit`: no known vulnerabilities.

**Risks/blockers:**

- Strict schema may break existing user artifacts. Provide migration notes and keep optional fields optional where needed.

### Task 6: Freeze Spec/Package Version Policy

**DoD:** API quality, Docs, Release & distribution, Repo hygiene

**Status:** Complete in Phase 3 Task 6.

**Estimate:** 1 cycle

**Dependencies:** Tasks 2-5 should be decided first because they affect public contract semantics.

**Files likely touched in Phase 3:**

- `src/agent_contracts/_version.py`
- `schemas/agent-contract.schema.json`
- `src/agent_contracts/schemas/agent-contract.schema.json`
- `spec/SPECIFICATION.md`
- `README.md`
- `CHANGELOG.md`
- `action.yml`
- `AGENT_CONTRACT.yaml`
- examples under `examples/`

**Plan:**

- [x] Decide whether contract spec version tracks package major/minor or evolves independently.
- [x] For `1.0.0`, make package version, README release references, action pin guidance, changelog, spec title, and examples consistent.
- [x] Document semver policy for Python API, CLI, contract schema, verdict schema, and action behavior.

**Decision:**

- Package versions and `agent_contract` spec versions are distinct SemVer streams.
- For the planned stable release, `aicontracts 1.0.0` implements contract spec `1.0.0` and the stable verdict artifact schema.
- Later package patch or minor releases may continue to implement contract spec `1.0.0`; the spec version changes only when YAML contract or verdict artifact semantics change.
- `identity.version` remains the version of the agent described by the contract and can differ from both the package version and the spec version.

**Verification:**

- `python3 -m ruff check src/ tests/`: passed.
- `python3 -m pytest --cov=agent_contracts --cov-report=term-missing`: passed, 211 passed, 6 skipped, 91% coverage.
- `python3 -m mypy src/agent_contracts`: passed.
- CLI smoke checks passed: `validate AGENT_CONTRACT.yaml`, `validate examples/support_triage.yaml`, and `check-compat examples/support_triage.yaml examples/support_triage.yaml`.
- `python3 -m pip_audit . --progress-spinner off`: passed, no known vulnerabilities found.
- `git diff --check`: passed.

**Acceptance:**

- No public doc says `v0.1.0` unless it is historical.
- Users can tell whether `agent_contract: "1.0.0"` is required, accepted, or distinct from package `1.0.0`.
- Action examples use the intended release tag.

**Risks/blockers:**

- No Task 6 blocker remains. `1.0.0` is prepared in source/docs but must not be described as published until both the PyPI package and `v1.0.0` GitHub tag exist.

### Task 7: Finalize Adapter Verdict Behavior

**DoD:** Value, Stability, Observability, Docs, Tests

**Status:** Complete in Phase 3 Task 7.

**Estimate:** 3 cycles

**Dependencies:** Task 5 should land first so adapters emit schema-valid artifacts.

**Files likely touched in Phase 3:**

- `src/agent_contracts/adapters/claude_agent.py`
- `src/agent_contracts/adapters/openai_agents.py`
- `src/agent_contracts/adapters/langchain.py`
- tests under `tests/test_adapters/`
- `README.md`
- new docs under `docs/` if docs are allowed in Phase 3

**Plan:**

- [x] For each adapter, define exactly when the run starts, when tool/file/shell/network effects are checkable, and when verdict finalization happens.
- [x] Add explicit finalization helpers if host hooks cannot guarantee finalization automatically.
- [x] Ensure adapter examples call finalization reliably.
- [x] Test pass, blocked, failed, and unexpected-error paths for each adapter where host SDK APIs allow.

**Behavior:**

- Claude Agent SDK: `PreToolUse` can deny generic tools and common inspectable native effects before execution; callers must call `finalize_run()` after the query loop because this adapter has no host run-end hook.
- OpenAI Agents SDK: `on_tool_start` can deny generic tool names before tool execution, after the model has selected the tool; native file/shell/network arguments are not visible in this hook surface; `on_agent_end` finalizes.
- LangChain: `on_tool_start` can deny generic tools and conventional inspectable native wrappers such as `bash`, `read_file`, `write_file`, and `web_fetch`; `on_chain_end` finalizes.
- Adapter finalization records required failure checks when completion or output was not observed, so partially observed runs do not pass silently.

**Verification:**

- `python3 -m pytest tests/test_adapters -q`: passed, optional real-SDK checks skipped when SDK packages were absent.
- `python3 -m ruff check src/ tests/`: passed.
- `python3 -m pytest --cov=agent_contracts --cov-report=term-missing`: passed, 228 passed, 6 skipped, 91% coverage.
- `python3 -m mypy src/agent_contracts`: passed.
- CLI smoke checks passed: `validate AGENT_CONTRACT.yaml`, `validate examples/support_triage.yaml`, and `check-compat examples/support_triage.yaml examples/support_triage.yaml`.
- `python3 -m pip_audit . --progress-spinner off`: passed, no known vulnerabilities found.
- `git diff --check`: passed.

**Acceptance:**

- Supported adapter paths can produce a schema-valid verdict artifact.
- Adapter docs honestly state pre-execution versus post-decision limitations.
- README's "every meaningful run can emit one artifact" claim matches behavior.

**Risks/blockers:**

- No Task 7 blocker remains. OpenAI Agents SDK does not expose native file/shell/network arguments through the hook surface used here, so those effects remain CI-gated unless users wrap them as named tools.

### Task 8: Harden CLI And GitHub Action Gate

**DoD:** Value, Stability, Tests, Release & distribution, Observability

**Status:** Complete in Phase 3 Task 8.

**Estimate:** 2 cycles

**Dependencies:** Task 5 must land first.

**Files likely touched in Phase 3:**

- `src/agent_contracts/cli.py`
- `action.yml`
- `.github/workflows/ci.yml`
- `tests/test_cli.py`
- possible action fixture workflow/tests
- `README.md`

**Plan:**

- [x] Add CLI tests for verdict validation errors and `--fail-on-warn`.
- [x] Add an action fixture or scripted smoke test that exercises `action.yml` behavior with pass/fail verdicts.
- [x] Confirm action install pin strategy for `1.0.0`.
- [x] Improve action output for multiple contract inputs if needed.

**Results:**

- Retained the existing `tests/test_cli.py` additions for verdict schema failures and `--fail-on-warn`; they passed unchanged and already cover the CLI half of this task.
- Added a lightweight local smoke test in `tests/test_action_yml.py` that parses `action.yml` and asserts the critical shell semantics are present: pinned `aicontracts==1.0.0` install, `fail-on-warning` handling, `fail-on-warn-outcome` mapping to `--fail-on-warn`, `check-verdict` invocation, and fail-closed exit behavior.
- Verified the release-pin guidance against live PyPI state: `aicontracts 0.2.0` is still the latest published version, so the existing README and action comments about not cutting `v1.0.0` before publishing `aicontracts==1.0.0` remain accurate. No README wording change was required.
- Reviewed multi-contract action output behavior and left it unchanged for `1.0.0`; the current grouped validation logs plus final outputs are acceptable for this release slice.

**Verification:**

- `python3 -m ruff check src/ tests/`: passed.
- `python3 -m pytest --cov=agent_contracts --cov-report=term-missing`: passed, 234 passed, 6 skipped, 91% coverage.
- `python3 -m mypy src/agent_contracts`: passed.
- `python3 -m agent_contracts.cli validate AGENT_CONTRACT.yaml`: passed.
- `python3 -m agent_contracts.cli validate examples/support_triage.yaml`: passed.
- `python3 -m agent_contracts.cli check-compat examples/support_triage.yaml examples/support_triage.yaml`: passed.
- `python3 -m pytest tests/test_action_yml.py -q`: passed, 3 tests.
- `python3 -m pip_audit . --progress-spinner off`: passed, no known vulnerabilities found.
- `git diff --check`: passed.

**Acceptance:**

- CLI and action gate blocked/fail/warn/pass outcomes consistently.
- Action docs include `v1` or `v1.0.0` usage guidance.
- CI runs an action smoke path or equivalent local composite-action validation.

**Risks/blockers:**

- No Task 8 blocker remains. Local coverage uses a Python smoke test that inspects composite-action shell semantics instead of invoking a GitHub-hosted runner or Docker, which is sufficient for this release slice and keeps the test portable.

### Task 9: Add Security And Release Hygiene

**DoD:** Security, Repo hygiene, Release & distribution, Docs

**Status:** Complete in Phase 3 Task 9.

**Estimate:** 2 cycles

**Dependencies:** Task 1 should land first.

**Files likely touched in Phase 3:**

- `SECURITY.md`
- `CONTRIBUTING.md`
- `CODEOWNERS`
- `.github/dependabot.yml`
- `.github/workflows/ci.yml`
- `.github/workflows/publish.yml`
- `README.md`
- `CHANGELOG.md`

**Plan:**

- [x] Add security reporting policy.
- [x] Add contributor setup and canonical commands.
- [x] Add ownership/review routing.
- [x] Add Dependabot or equivalent dependency update automation.
- [x] Add `pip-audit` gates for core and optional extras.
- [x] Make release hygiene checks explicit and remove implicit reliance on tools not installed by the workflow.

**Results:**

- Added `SECURITY.md` with a private-reporting-first disclosure path and public issue fallback only for non-sensitive hardening requests.
- Added `CONTRIBUTING.md` with setup, canonical local gates, adapter-extra guidance, release hygiene, and security hygiene notes.
- Added `CODEOWNERS`, Dependabot config for Python and GitHub Actions, bug/security-hardening issue templates, and a PR template with required verification.
- CI now runs `check-compat` alongside canonical validation and audits the clean CI environment with `pip-audit`.
- Release verification installs adapter extras, `build`, `twine`, and `pip-audit` explicitly, audits the release environment, and checks built wheel/sdist contents for internal-only files with a Python standard-library script instead of relying on unavailable shell tools.

**Verification:**

- `python3 -m ruff check src/ tests/`: passed.
- `python3 -m pytest --cov=agent_contracts --cov-report=term-missing`: passed, 234 passed, 6 skipped, 91% coverage.
- `python3 -m mypy src/agent_contracts`: passed.
- `python3 -m agent_contracts.cli validate AGENT_CONTRACT.yaml`: passed.
- `python3 -m agent_contracts.cli validate examples/support_triage.yaml`: passed.
- `python3 -m agent_contracts.cli check-compat examples/support_triage.yaml examples/support_triage.yaml`: passed.
- `python3 -m pip_audit . --progress-spinner off`: passed, no known vulnerabilities found.
- `git diff --check`: passed.

**Acceptance:**

- CI fails on known vulnerable dependencies.
- External contributors can find setup, test, release, and security-reporting instructions.
- Release workflow has no implicit dependency on unavailable command-line tools.

**Risks/blockers:**

- Some hygiene files are public docs and should avoid internal-only AGENTS/OMX details.

### Task 10: Add Performance Baselines

**DoD:** Performance, Tests, Stability, Docs

**Estimate:** 2 cycles

**Dependencies:** Tasks 2 and 4 should land first so benchmarks reflect final semantics.

**Files likely touched in Phase 3:**

- performance tests or benchmark files under `tests/` or `benchmarks/`
- `src/agent_contracts/effects.py`
- `src/agent_contracts/postconditions.py`
- `src/agent_contracts/init_from_trace.py`
- `README.md` or `spec/SPECIFICATION.md`

**Plan:**

- [x] Add repeatable benchmarks for 1, 100, and 10,000 effect checks.
- [x] Add baseline for postcondition evaluation with small and large postcondition sets.
- [x] Add trace bootstrap benchmark for large JSONL traces.
- [x] Define acceptable thresholds and document them as release guardrails.

**Results:**

- Added `benchmarks/performance-baselines.json` with concrete local baselines and conservative release budgets for effect authorization, postcondition evaluation, and JSONL trace bootstrap.
- Added `tests/test_performance_baselines.py`, which runs in the normal pytest suite and enforces the release budgets.
- Documented the release guardrails in `benchmarks/README.md` and summarized the enforced budgets in `README.md`.
- Local baseline medians on May 4, 2026: 1 effect check 0.004 ms, 100 effect checks 2.47 ms, 10,000 effect checks 200.45 ms, 5 postconditions 0.10 ms, 1,000 postconditions 19.31 ms, and 2,500 JSONL trace bootstrap 28.24 ms.

**Verification:**

- `python3 -m pip install -e ".[dev]"`: passed.
- `python3 -m ruff check src/ tests/`: passed.
- `python3 -m pytest tests/test_performance_baselines.py -q`: failed before the baseline artifact existed, then passed after adding it.
- `python3 -m pytest --cov=agent_contracts --cov-report=term-missing`: passed, 237 passed, 6 skipped, 91% coverage.
- `python3 -m mypy src/agent_contracts`: passed.
- `python3 -m agent_contracts.cli validate AGENT_CONTRACT.yaml`: passed.
- `python3 -m agent_contracts.cli validate examples/support_triage.yaml`: passed.
- `python3 -m agent_contracts.cli check-compat examples/support_triage.yaml examples/support_triage.yaml`: passed.
- `python3 -m pip index versions aicontracts`: PyPI latest verified as `0.2.0`; local editable install is `1.0.0`.
- `python3 -m pip_audit . --progress-spinner off`: passed, no known vulnerabilities found.

**Acceptance:**

- Release has concrete baseline numbers for hot paths.
- Benchmarks are deterministic enough for local comparison even if not hard-gated in every CI run.
- Any pattern caching or streaming optimization remains behavior-preserving.

**Risks/blockers:**

- Performance gates can be flaky in CI. Prefer benchmark reporting unless there is a stable threshold.

### Task 11: Complete Docs And Demo Proof

**DoD:** Value, Docs, Observability, Release & distribution

**Status:** Complete (2026-05-04)

**Estimate:** 3 cycles

**Dependencies:** Tasks 2-8 should land first so docs match behavior.

**Files likely touched in Phase 3:**

- `README.md`
- `spec/SPECIFICATION.md`
- examples under `examples/`
- new docs/demo files if docs are allowed in Phase 3
- `CHANGELOG.md`

**Plan:**

- [x] Add end-to-end demos for blocked file write, blocked shell command, failed checks, and green pass artifact.
- [x] Add host-specific integration docs for Claude Code, Codex, Claude Agent SDK, OpenAI Agents SDK, and LangChain.
- [x] Add sample verdict artifacts and CI annotations/PR-review guidance.
- [x] Update changelog with migration notes from `0.2.0` to `1.0.0`.
- [x] Add release-branch install-to-first-working-example path in README.
- [x] Add top 3 README adoption questions and downstream debugging guidance.
- [x] Add generated API reference and generator/check command.
- [x] Add troubleshooting page covering the top five audit/demo adoption questions.

**Acceptance:**

- A skeptical repo owner can adopt the package from README plus examples.
- Docs make host limitations clear and do not overclaim hard-stop coverage.
- Demo artifacts validate against the verdict schema.

**Verification:** Completed for Phase 3 Task 11.

- `python3 -m pip install -e ".[dev]"`: passed.
- `python3 examples/run_green_pass.py --artifact-dir /tmp/aicontracts-task11-demo`: passed, emitted `pass` / `allowed`.
- `python3 examples/run_blocked_file_write.py --artifact-dir /tmp/aicontracts-task11-demo`: passed, emitted expected `blocked` / `blocked`.
- `python3 examples/run_blocked_command.py --artifact-dir /tmp/aicontracts-task11-demo`: passed, emitted expected `blocked` / `blocked`.
- `python3 examples/run_failed_checks.py --artifact-dir /tmp/aicontracts-task11-demo`: passed, emitted expected `fail` / `failed`.
- `python3 -m ruff check src/ tests/`: passed.
- `python3 -m pytest --cov=agent_contracts --cov-report=term-missing`: passed, 240 passed, 6 skipped, 91% coverage.
- `python3 -m mypy src/agent_contracts`: passed.
- CLI smoke checks for `AGENT_CONTRACT.yaml`, `examples/support_triage.yaml`, and `check-compat examples/support_triage.yaml examples/support_triage.yaml`: passed.
- `python3 -m pip index versions aicontracts`: PyPI latest verified as `0.2.0`; local editable install is `1.0.0`.
- `python3 -m pip_audit . --progress-spinner off`: passed, no known vulnerabilities found.
- `python3 scripts/generate_api_reference.py --check`: passed.
- All YAML files under `examples/*.yaml` loaded successfully.
- `python3 -m build && python3 -m twine check dist/*`: passed.
- Distribution hygiene dry run confirmed the sdist contains public docs/examples and neither wheel nor sdist contains internal-only files.
- `git diff --check`: passed before final commit.

**Risks/blockers:**

- Docs may reveal that some host integrations are weaker than desired. Keep the CI verdict gate as source of truth.

### Task 12: External User Validation

**DoD:** Value, Stability, Docs, Release & distribution

**Estimate:** 3 cycles plus calendar time

**Dependencies:** Tasks 1-11 complete.

**Files likely touched in Phase 3:**

- `README.md`
- examples/docs from Task 11
- `CHANGELOG.md`
- release checklist notes

**Plan:**

- [ ] Select at least two external or external-like repos: one Python repo and one JS/TS repo.
- [ ] Install from the release candidate build.
- [ ] Generate or adapt `AGENT_CONTRACT.yaml`.
- [ ] Run local validate/check-verdict flow.
- [ ] Add GitHub Action gate.
- [ ] Record adoption friction and fix release-blocking issues.

**Acceptance:**

- At least two non-maintainer workflows can run the contract gate without hand editing internals.
- External validation does not identify a P0/P1 blocker.
- Any remaining friction is documented as non-blocking or tracked for post-1.0.

**Risks/blockers:**

- External validation requires calendar coordination and cannot be completed by implementation alone.

### Task 13: Release Candidate And Final Release

**DoD:** Release & distribution, Security, Tests, Docs, Repo hygiene

**Estimate:** 2 cycles plus soak time

**Dependencies:** Tasks 1-12 complete.

**Files likely touched in Phase 3:**

- `src/agent_contracts/_version.py`
- `CHANGELOG.md`
- `README.md`
- `action.yml`
- release workflow metadata as needed

**Plan:**

- [ ] Cut `1.0.0rc1` or equivalent pre-release artifact if PyPI flow supports it.
- [ ] Run full local gates and GitHub matrix.
- [ ] Run dependency audit gates.
- [ ] Run action smoke gate.
- [ ] Run external-user validation on RC.
- [ ] Cut `v1.0.0` only after RC gates pass.

**Acceptance:**

- GitHub release and PyPI package are published for `1.0.0`.
- GitHub Action usage is documented with a stable tag.
- Changelog includes security, migration, and breaking-change notes.

**Risks/blockers:**

- RC gate must remain blocked until implementation and external validation are done.

## Dependency Graph

- Task 1 has no dependencies and should be first.
- Task 2 has no dependencies and can run alongside Task 1.
- Task 3 depends on Task 2.
- Task 4 has no dependencies and can run alongside Task 1 or 2.
- Task 5 depends on Task 4.
- Task 6 depends on Tasks 2-5.
- Task 7 depends on Task 5.
- Task 8 depends on Task 5.
- Task 9 depends on Task 1.
- Task 10 depends on Tasks 2 and 4.
- Task 11 depends on Tasks 2-8.
- Task 12 depends on Tasks 1-11.
- Task 13 depends on Tasks 1-12.

## Audit Blocker Handling Matrix

| Audit blocker | Handling task | Status |
|---|---:|---|
| Vulnerable optional `langchain-core==1.2.26` pin | Task 1 | Complete |
| Filesystem path traversal canonicalization | Task 2 | Complete |
| Fail-closed missing effect sub-surfaces | Task 3 | Complete |
| `eval:` postconditions fake-green behavior | Task 4 | Complete |
| Spec/package version mismatch | Task 6 | Complete |
| Verdict schema validation | Task 5 | Complete |
| Adapter verdict finalization | Task 7 | Complete |
| Docs/security/perf/release hygiene | Tasks 9-13 | Planned, blocks release |

## RC, External-User, And Release Gates

### RC Gate

Status: **BLOCKED until Tasks 1-11 are implemented.**

Required evidence:

- Full local canonical gates pass.
- GitHub CI matrix passes on Python 3.9, 3.10, 3.11, 3.12, 3.13.
- Core and optional extras dependency audits pass.
- Verdict schema tests pass.
- GitHub Action smoke gate passes.
- Changelog and migration notes are complete.

### External-User Gate

Status: **BLOCKED until RC artifact and demo docs exist.**

Required evidence:

- At least two external or external-like repositories install the RC.
- Both produce a valid `AGENT_CONTRACT.yaml`.
- Both run `validate` and `check-verdict`.
- At least one uses the GitHub Action gate.
- No P0/P1 adoption blocker remains open.

### Final Release Gate

Status: **BLOCKED until RC and external-user gates pass.**

Required evidence:

- `1.0.0` version/tag/package/action/docs are consistent.
- PyPI wheel and sdist are built and checked.
- GitHub release notes include breaking changes and security notes.
- Public docs do not overclaim adapter enforcement coverage.
- Release owner signs off on DoD sections: Value, API quality, Stability, Tests, Security, Performance, Docs, Release & distribution, Repo hygiene, Observability.

## Phase 3 Starting Point

Task 7 is complete. Continue Phase 3 with Task 8: harden CLI and GitHub Action gate.
