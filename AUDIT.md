# agent-contracts Phase 1 Audit

Date: 2026-05-04
Scope: Phase 1 audit only. No code, config, package metadata, or docs were modified.

## Executive Summary

`agent-contracts` is a coherent alpha package with a strong repo-local coding/build-agent wedge, passing CI on the published `v0.2.0` release commit and passing local core gates with 90% coverage. It is not yet ready for a stable, secure major release without follow-up work.

The highest-priority release blockers are:

1. Optional `aicontracts[langchain]` pins vulnerable `langchain-core==1.2.26` (`CVE-2026-40087`; fixed in `1.2.28` or `0.3.84`).
2. Filesystem scope matching can authorize traversal strings before canonical path matching, e.g. a `src/**` write pattern matches raw `src/../.env` even though the resolved path is `.env`.
3. "Default deny" is conditional on a sub-surface being configured: missing `filesystem` or `shell` authorization currently allows those effects.
4. `eval:` postconditions are accepted as passing without evaluator integration, which can create fake-green contracts.
5. The public spec remains labeled `v0.1.0` while the shipped package, action, and changelog are `0.2.0`.

## Version And Release Target

- Local package version: `0.2.0` from `src/agent_contracts/_version.py`.
- Published package: `aicontracts 0.2.0` verified against PyPI JSON and package metadata.
- PyPI files for `0.2.0`: wheel and sdist uploaded on 2026-04-09.
- GitHub release: `v0.2.0`, published 2026-04-09, current `HEAD` and `origin/main` at `28b521d`.
- Package status classifier: Alpha.

Target version recommendation:

- Mission target should be `1.0.0`, not `0.3.0`, if the goal is a stable, secure, valuable major release with semver-stable public API/spec/CLI behavior.
- A security-only patch before the major release should be `0.2.1`.
- A minor pre-1.0 feature/stabilization train could be `0.3.0`, but it should not be marketed as the stable major release.

## Evidence Collected

Required docs read:

- `/Users/piyush/GitHub/AGENTS.md`
- `/Users/piyush/GitHub/agent-contracts/AGENTS.md`
- `README.md`
- `docs/plans/2026-04-02-agent-contracts-coding-agent-roadmap.md`
- `docs/plans/2026-04-02-agent-contracts-omx-handoff-spec.md`

Commands and results:

- `git status --short`: clean before audit writes.
- `python -m pip install -e ".[dev]"`: blocked locally because `python` is not on PATH.
- `python3 -m pip install -e ".[dev]"`: passed using Python 3.9.6 fallback.
- `python3 -m ruff check src/ tests/`: passed.
- `python3 -m pytest --cov=agent_contracts --cov-report=term-missing`: passed, 190 passed, 6 skipped, 90% coverage.
- `python3 -m mypy src/agent_contracts`: passed.
- CLI smoke checks: `validate AGENT_CONTRACT.yaml`, `validate examples/support_triage.yaml`, and `check-compat examples/support_triage.yaml examples/support_triage.yaml` all passed.
- `pip-audit .`: no known vulnerabilities for core resolved project dependencies.
- Optional extras audit via Python 3.12 requirement set: 1 vulnerability in `langchain-core==1.2.26`.
- `gh issue list --state open --limit 500`: authenticated and returned no open issues.
- `gh run view 24201202052`: latest CI for current release commit passed across Python 3.9, 3.10, 3.11, 3.12, 3.13.

Local environment notes:

- `/usr/bin/python3` is Python 3.9.6.
- No `python` executable is on PATH locally, so canonical commands require either a `python` shim or docs adjustment.
- Optional SDK integration tests skipped locally because Python 3.9 environment does not install Python 3.10+ adapter extras; CI covers those extras on 3.10+.

## Public API Surface Inventory

Python package:

- Package name: `aicontracts`
- Import package: `agent_contracts`
- Typed marker: `src/agent_contracts/py.typed`
- Core exports in `agent_contracts.__all__`:
  - Version: `__version__`
  - Data model: `Contract`, `ContractIdentity`, `PostconditionDef`, `PreconditionDef`, `EffectsAuthorized`, `EffectsDeclared`, `FilesystemAuthorization`, `ShellAuthorization`, `ResourceBudgets`, `DelegationRules`, `FailureModel`, `ObservabilityConfig`, `VersioningConfig`, `SLOConfig`
  - Loading/validation: `load_contract`, `validate_contract`, `ContractLoadError`
  - Tiering: `assess_tier`, `recommend_upgrades`, `TierRecommendation`
  - Runtime enforcement: `ContractEnforcer`, `ContractViolation`, `RunCheckResult`, `RunVerdict`, `enforce_contract`
  - Effects/budgets: `EffectGuard`, `EffectDeniedError`, `BudgetTracker`, `BudgetExceededError`
  - Conditions/events: `PostconditionError`, `PreconditionError`, `ViolationEvent`, `ViolationEmitter`
  - Composition: `check_compatibility`, `CompatibilityReport`

Adapters:

- `agent_contracts.adapters.claude_agent.ContractHooks`
- `agent_contracts.adapters.openai_agents.ContractRunHooks`
- `agent_contracts.adapters.langchain.ContractCallbackHandler`

CLI surface:

- Console script: `aicontracts`
- Module entry: `python -m agent_contracts.cli`
- Commands:
  - `validate`
  - `init`
  - `check-compat`
  - `check-verdict`
  - `test`

Schema/spec surfaces:

- Machine schema: `schemas/agent-contract.schema.json`
- Packaged schema: `src/agent_contracts/schemas/agent-contract.schema.json`
- Human spec: `spec/SPECIFICATION.md`
- MCP proposal: `mcp/x-agent-contract.md`
- Canonical contract file: `AGENT_CONTRACT.yaml`
- Examples: `examples/*.yaml`

GitHub Action:

- Composite action: `action.yml`
- Inputs: `contract`, `verdict`, `fail-on-warning`, `fail-on-warn-outcome`, `python-version`
- Outputs: `outcome`, `tier`, `verdict-outcome`
- Current action install pin: `aicontracts==0.2.0`

Distribution:

- Wheel and sdist published to PyPI.
- Release workflow uses PyPI trusted publishing and GitHub release generation.
- CI matrix supports core Python 3.9+ and adapter extras on 3.10+.

## GitHub Issues

GitHub CLI was available and authenticated as `pyyush`.

Open issues: none.

Triage:

- No open issues to label.
- Audit-discovered release blockers should become issues or a `RELEASE_PLAN.md` task list in the next phase.

## Known Bugs And Stability Gaps

Security/stability blockers:

- Filesystem authorization checks raw user input before canonical path matching. This allows path traversal shaped like `src/../.env` to match `src/**`.
- Missing sub-surface configuration permits by default. If `effects.authorized` exists but omits `filesystem` or `shell`, file and shell operations are allowed. This conflicts with the mission's fail-closed coding mode.
- `eval:` postconditions currently pass automatically. That is acceptable only as an explicit placeholder, not as a stable contract behavior.
- Optional LangChain extra pins a vulnerable version.
- Shell command matching is intentionally strict but too coarse for common safe shell workflows; v0.3.x roadmap mentions a future `shlex` matcher.
- Adapter hooks are partial:
  - Claude hook currently enforces tool names but does not map file/shell/network semantics from host tool payloads.
  - OpenAI/LangChain adapters observe some hooks but do not finalize verdict artifacts automatically.
- `check-verdict` trusts JSON shape enough to load and inspect but does not validate a formal verdict artifact schema.
- Composition checks focus on schemas/tools/budgets and do not yet cover filesystem, shell, or network compatibility deeply.
- Postcondition expression evaluator is intentionally narrow and has no formal grammar, which may create surprising contract authoring behavior.
- Contract schema allows broad `additionalProperties`, which preserves extension compatibility but limits typo detection for stable 1.0 authoring.

Release polish gaps:

- CLI install warning: `aicontracts` script installed to a user bin directory not on PATH in this local environment.
- Canonical commands in AGENTS.md use `python`, but local PATH only has `python3`.
- README says "Every run emits one durable verdict.json"; code supports emission when `finalize_run()` is called, but host integrations do not guarantee every run finalizes.

## Test Coverage

Current local coverage:

- Total: 90%
- Result: 190 passed, 6 skipped
- Platform: macOS, Python 3.9.6

Lowest-coverage areas by file:

- `src/agent_contracts/cli.py`: 79%
- `src/agent_contracts/effects.py`: 85%
- `src/agent_contracts/init_from_trace.py`: 84%
- `src/agent_contracts/enforcer.py`: 86%
- `src/agent_contracts/violations.py`: 86%
- `src/agent_contracts/adapters/langchain.py`: 87%

Skipped local tests:

- 2 Claude SDK tests skipped: `claude_agent_sdk` not installed locally.
- 2 LangChain tests skipped: `langchain_core` not installed locally.
- 2 OpenAI Agents tests skipped: `agents` not installed locally.

Coverage gap for 1.0:

- Add regression coverage for canonicalized filesystem path traversal.
- Add tests proving missing coding-agent effect sub-surfaces fail closed in coding mode.
- Add verdict schema validation tests.
- Add real or simulated adapter finalization tests that prove verdict artifacts are emitted.
- Add CLI tests for malformed verdict artifacts and multiple contract inputs.

## Dependency Audit

Core dependency audit:

- Tool: `pip-audit 2.9.0`
- Command: `python3 -m pip_audit . --format json --progress-spinner off`
- Result: no known vulnerabilities for resolved core project dependencies.
- Audited core packages included `pyyaml 6.0.3`, `jsonschema 4.25.1`, `click 8.1.8`, and transitive schema dependencies.

Optional extras audit:

- Tool: `uvx --python /opt/homebrew/bin/python3.12 pip-audit`
- Requirement set included core dependencies plus `opentelemetry-api`, `langchain-core==1.2.26`, `openai-agents==0.13.5`, `claude-agent-sdk==0.1.56`.
- Result: one known vulnerability:
  - Package: `langchain-core==1.2.26`
  - ID: `CVE-2026-40087`
  - Alias: `GHSA-926x-3r5x-gfhw`
  - Fixed versions reported: `1.2.28`, `0.3.84`
  - Impact: unsafe f-string prompt-template validation when applications accept untrusted template strings.

Published version checks against PyPI:

- `aicontracts`: latest `0.2.0`
- `langchain-core`: latest `1.3.2`; pinned `1.2.26` exists; fixed `1.2.28` exists.
- `openai-agents`: PyPI JSON latest `0.15.1`; pinned `0.13.5` exists.
- `claude-agent-sdk`: PyPI JSON latest `0.1.72`; pinned `0.1.56` exists.

## CI Status

Latest CI run for current `HEAD`/`v0.2.0`:

- Run: `24201202052`
- Commit: `28b521da5d49fa0bc64ace70677d64c82c15d523`
- Status: success
- Matrix:
  - Python 3.9: success
  - Python 3.10: success
  - Python 3.11: success
  - Python 3.12: success
  - Python 3.13: success

Latest release workflow:

- Run: `24201398853`
- Tag: `v0.2.0`
- Status: success

CI gaps:

- CI does not run `pip-audit`.
- CI does not validate a verdict artifact schema.
- CI does not perform release hygiene on normal PRs; public hygiene check exists only in the tag release workflow.
- CI does not test the composite GitHub Action against an actual fixture workflow.

## Docs Gap Analysis Against Mission DoD

Value:

- Strong README positioning and demos exist.
- Missing a design-partner/public adoption proof story.
- Missing a concrete end-to-end demo transcript showing blocked file, blocked shell, failed checks, and green pass artifact.

API quality:

- Public Python exports are clear, but no API stability policy exists.
- Spec/package version relationship is ambiguous.
- Schema is permissive enough that author typos may survive validation.

Stability:

- Canonical workflow is documented and passing.
- Host adapter limitations are acknowledged, but exact coverage per host is not documented in enough operational detail.

Tests:

- Coverage is good for alpha, but 1.0 needs security regression tests and real adapter finalization tests.

Security:

- Shell metacharacter threat model is documented.
- Missing SECURITY.md.
- Dependency audit is not in CI.
- LangChain optional extra is vulnerable.
- Filesystem traversal issue is undocumented.

Performance:

- No performance targets or benchmark docs.
- Hot paths are simple, but no measurements exist for large contracts, long traces, or large check sets.

Docs:

- README is clear.
- Human spec still says `v0.1.0`.
- No dedicated integration guides for Claude Code/Codex beyond README examples.

Release & distribution:

- PyPI, GitHub release, action, changelog, and release workflow exist.
- Action is pinned to a package version and must be updated every release.
- No formal release checklist for major release.

Repo hygiene:

- `.gitignore` covers local artifacts and internal docs.
- Missing CONTRIBUTING.md, SECURITY.md, CODEOWNERS, dependabot.
- `AGENTS.md` and `docs/plans/` are intentionally ignored locally and absent from the tracked public release tree.

Observability:

- Violation events and verdict artifact structures exist.
- No formal JSON Schema for verdict artifacts.
- No examples of integrating artifact output with CI annotations or PR comments.

## Repo Hygiene Gap Analysis

Good:

- Worktree was clean before audit writes.
- Internal-only files are gitignored.
- Release workflow checks that internal-only files are not tracked.
- Package has `py.typed`.
- Changelog exists.
- License exists.

Gaps:

- `SECURITY.md` missing.
- `CONTRIBUTING.md` missing.
- CODEOWNERS missing.
- Dependabot config missing.
- No lockfile or constraints file for repeatable dev installs.
- Release hygiene check relies on `rg` in GitHub Actions without an explicit install step; it works on current runners but is an implicit tool dependency.
- Public release tree does not include repo-local AGENTS instructions, by design, but that means external contributors lack those workflow cues unless CONTRIBUTING.md is added.

## Performance Hot Paths

Likely hot paths:

- Filesystem authorization: path normalization plus glob matching per file effect.
- Shell command authorization: metacharacter scan, normalization, and glob matching per command.
- Postcondition evaluation: repeated expression parsing/evaluation for each postcondition.
- JSON Schema validation: contract load and input/output validation.
- Trace bootstrap: JSONL reading and path/tool/shell inference across many events.
- Verdict writing: JSON serialization and filesystem write at run finalization.

Performance risks:

- `fnmatch` over many patterns is O(number of patterns) per effect.
- Postconditions are reparsed on every evaluation.
- Trace bootstrap loads all traces into memory before extraction.
- Large verdict artifacts could grow with many violations/checks without truncation or streaming.

Recommended performance work:

- Add baseline benchmarks for 1, 100, and 10,000 effect checks.
- Cache compiled/normalized pattern sets.
- Stream trace bootstrap where possible.
- Define artifact size expectations and truncation behavior for large evidence payloads.

## Prioritized Work List Mapped To DoD

P0:

1. Fix optional `langchain-core` vulnerability by moving to a non-vulnerable pinned version or temporarily removing the LangChain extra. DoD: Security, Release & distribution.
2. Fix filesystem authorization to match only canonical repo-relative paths, reject traversal escapes, and add regression tests. DoD: Security, Stability, Tests, API quality.
3. Define and enforce fail-closed coding mode for missing `filesystem` and `shell` sub-surfaces. DoD: Value, Security, Stability, API quality, Docs.
4. Replace auto-pass `eval:` postconditions with explicit unsupported/adapter-required semantics. DoD: Value, Stability, Security, Docs.
5. Add a verdict artifact JSON Schema and validate `check-verdict` input against it. DoD: API quality, Stability, Security, Observability, Tests.

P1:

6. Align spec docs and examples with the shipped package/spec version policy before 1.0. DoD: Docs, API quality, Release & distribution.
7. Add CI dependency audit for core plus optional extras. DoD: Security, Release & distribution, Repo hygiene.
8. Add host integration guides for Claude Code, Codex, OpenAI Agents SDK, Claude Agent SDK, and LangChain with honest pre/post-execution limits. DoD: Value, Docs, Stability.
9. Ensure adapters finalize or document how to finalize verdict artifacts in every supported host path. DoD: Value, Observability, Stability, Docs.
10. Add composite GitHub Action fixture tests. DoD: Tests, Release & distribution, Stability.

P2:

11. Add `SECURITY.md`, `CONTRIBUTING.md`, CODEOWNERS, and dependabot. DoD: Security, Repo hygiene.
12. Add performance benchmarks and target thresholds for effect checks, postconditions, trace bootstrap, and verdict finalization. DoD: Performance, Tests.
13. Improve composition checks for filesystem, shell, and network compatibility. DoD: API quality, Stability, Security.
14. Add a major-release checklist and semver policy. DoD: Release & distribution, Docs, Repo hygiene.
15. Add sample verdict artifacts and CI annotation examples. DoD: Observability, Docs, Value.

## DoD Delta Inventory

Value:

- Delta: prove adoption value with end-to-end demos and integration guides; fix behavior that undermines fake-green prevention.

API quality:

- Delta: freeze semver/spec policy, verdict schema, fail-closed semantics, and filesystem/shell matching semantics.

Stability:

- Delta: close traversal/default-allow/eval gaps and finalize verdict behavior consistently.

Tests:

- Delta: add security regressions, verdict schema tests, adapter finalization tests, action fixture tests, and performance tests.

Security:

- Delta: fix vulnerable LangChain pin, add dependency audit to CI, add SECURITY.md, fix filesystem traversal, and eliminate unsupported auto-pass postconditions.

Performance:

- Delta: add benchmarks and target thresholds for hot paths.

Docs:

- Delta: align spec versioning, add host-specific integration guides, add concrete demo walkthroughs.

Release & distribution:

- Delta: decide `1.0.0` criteria, add release checklist, update action pin strategy, add audit gates.

Repo hygiene:

- Delta: add contributor/security/ownership automation and repeatable dev dependency constraints.

Observability:

- Delta: formalize verdict schema, provide artifact examples, and ensure every supported runtime path writes a verdict.

