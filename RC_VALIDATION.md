# Agent Contracts 1.0 RC Validation Handoff

This document is the external-user validation handoff for `aicontracts 1.0.0`.
It prepares the RC workflow but does not claim that an RC exists, was published,
or was validated by an external user.

## Current RC Artifact Status

Fill these fields only after a real release candidate is cut.

| Field | Value |
|---|---|
| RC version | `1.0.0rc1` or `1.0.0-rc.1` |
| RC git commit | `TBD` |
| RC git tag | `TBD` |
| PyPI/TestPyPI URL | `TBD` |
| Wheel filename | `TBD` |
| sdist filename | `TBD` |
| Wheel SHA256 | `TBD` |
| sdist SHA256 | `TBD` |
| Release owner | `TBD` |
| RC cut date | `TBD` |
| Validation window | `TBD` |

RC validation cannot satisfy the release DoD until at least one real external
developer runs the RC in their own project and feedback is incorporated or
explicitly classified as non-blocking.

## Validator Requirements

Use at least two external or external-like repositories:

1. A Python project using `pytest` or an equivalent required check.
2. A JS/TS or mixed-language project that can still use the Python CLI as a
   repo-local CI gate.

At least one validator must be a real external developer who is not the release
owner. At least one validation run must exercise the GitHub Action gate.

Each validator records:

- repo name and URL or private-repo description
- validator name or handle
- operating system
- Python version
- package install source
- commands run
- generated/adapted `AGENT_CONTRACT.yaml`
- verdict artifact path
- GitHub Action run URL, if used
- adoption friction
- P0/P1 blockers, if any
- explicit pass/fail recommendation for `1.0.0`

## Clean-Project Install Smoke

Run this in a scratch directory outside this repository. Replace the package URL
or version with the actual RC artifact.

```bash
mkdir -p /tmp/aicontracts-rc-smoke
cd /tmp/aicontracts-rc-smoke
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install "<RC_WHEEL_URL_OR_PATH>"
# Or, for TestPyPI:
# python -m pip install --pre --index-url "<RC_INDEX_URL>" --extra-index-url https://pypi.org/simple "aicontracts==1.0.0rc1"
python -m agent_contracts.cli --version
python -m agent_contracts.cli init --template coding -o AGENT_CONTRACT.yaml
python -m agent_contracts.cli validate AGENT_CONTRACT.yaml
```

Record the full command output. If the generated starter contract does not
match the final stable `1.0.0` contract examples, record the difference as
release feedback before final publication.

## Repo Demo Smoke

Run this against the exact RC commit or tag. These commands verify the packaged
runtime, CLI, sample contracts, and schema-backed verdict artifacts.

```bash
git clone https://github.com/pyyush/agentcontracts.git aicontracts-rc
cd aicontracts-rc
git checkout "<RC_TAG_OR_COMMIT>"
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install ".[dev]"
python -m agent_contracts.cli validate AGENT_CONTRACT.yaml
python -m agent_contracts.cli validate examples/support_triage.yaml
python examples/run_green_pass.py --artifact-dir /tmp/aicontracts-rc-artifacts
python -m agent_contracts.cli check-verdict /tmp/aicontracts-rc-artifacts/green-pass.json
python examples/run_blocked_file_write.py --artifact-dir /tmp/aicontracts-rc-artifacts
python -m agent_contracts.cli check-verdict /tmp/aicontracts-rc-artifacts/blocked-file-write.json
```

Expected result:

- `validate` exits zero for both contracts.
- `run_green_pass.py` emits `outcome: pass` and `final_gate: allowed`.
- `check-verdict` exits zero for the green verdict.
- `run_blocked_file_write.py` emits `outcome: blocked` and `final_gate: blocked`.
- `check-verdict` exits non-zero for the blocked verdict.

The blocked verdict command is expected to fail; record the non-zero exit as
passing evidence if the printed outcome and final gate are `blocked`.

## External Project Adoption Flow

Run this in the validator's own repo.

```bash
python3 -m venv .venv-aicontracts-rc
. .venv-aicontracts-rc/bin/activate
python -m pip install --upgrade pip
python -m pip install "<RC_WHEEL_URL_OR_PATH>"
# Or, for TestPyPI:
# python -m pip install --pre --index-url "<RC_INDEX_URL>" --extra-index-url https://pypi.org/simple "aicontracts==1.0.0rc1"
python -m agent_contracts.cli init --template coding -o AGENT_CONTRACT.yaml
```

Edit `AGENT_CONTRACT.yaml` to match the repo's real surfaces:

- allowed read paths
- allowed write paths
- allowed shell commands
- required repo checks
- verdict artifact path
- budgets

Then run:

```bash
python -m agent_contracts.cli validate AGENT_CONTRACT.yaml
python -m agent_contracts.cli check-compat AGENT_CONTRACT.yaml AGENT_CONTRACT.yaml
```

Create one real verdict artifact using either a host adapter or the repo's
CI/demo integration, then run:

```bash
python -m agent_contracts.cli check-verdict "<PATH_TO_VERDICT_JSON>"
```

## GitHub Action Gate Smoke

At least one validator must add the action to a branch and link the run.
Before this can satisfy the RC gate, the action run must install the same RC
package artifact being validated. Until the stable `aicontracts==1.0.0`
package exists on PyPI, the action default stays pinned to the latest
published 0.x package. RC validators must override `package-spec` to the RC
wheel URL, local wheel path, or pre-release requirement.

```yaml
name: Agent Contract

on:
  pull_request:
  push:

jobs:
  contract:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pyyush/agentcontracts@<RC_TAG>
        with:
          contract: AGENT_CONTRACT.yaml
          verdict: .agent-contracts/runs/latest/verdict.json
          package-spec: "<RC_WHEEL_URL_OR_aicontracts==1.0.0rc1>"
          allow-prerelease: "true"
          # Optional for TestPyPI or a private package index:
          # pip-index-url: "<RC_INDEX_URL>"
          # pip-extra-index-url: "https://pypi.org/simple"
```

If the validator cannot produce a real agent verdict yet, they must still run
`validate` in CI and record what prevented `check-verdict` from running. That
does not satisfy the final DoD by itself.

## Feedback Form

Use one section per validating repo.

```markdown
## Validation Record: <repo>

- Validator:
- Repo:
- Repo language/runtime:
- OS:
- Python version:
- RC artifact:
- Install command:
- Contract path:
- Verdict artifact path:
- GitHub Action run:
- Commands run:
- Time from install to first valid contract:
- Time from install to first verdict gate:
- What worked:
- What was confusing:
- Missing docs:
- API/CLI issues:
- Security concerns:
- P0/P1 blockers:
- Non-blocking follow-ups:
- Validator recommendation: pass/fail
```

## Pass Criteria

The external-user gate passes only when all of these are true:

- at least two external or external-like repos install the RC
- at least one real external developer validates the RC in their own project
- at least one validation uses the GitHub Action gate
- every validation produces or checks a schema-valid verdict artifact
- no P0/P1 adoption blocker remains open
- feedback is incorporated or explicitly tracked as post-`1.0.0`
- package version, docs, action reference, and changelog all point to the same
  RC artifact

## Fail Criteria

The RC must not advance to final release if any of these are true:

- package install fails from the RC artifact on a supported Python version
- a generated or adapted contract cannot be validated without undocumented steps
- `check-verdict` accepts malformed verdict JSON
- a blocked or failed verdict exits zero without an explicit warning override
- adapter docs overclaim hard-stop coverage compared with observed behavior
- the GitHub Action cannot run the documented validate/check-verdict path
- any P0/P1 adoption blocker remains open

## Remote Repository Settings Evidence

Release-owner configuration update recorded on 2026-05-04 for
`pyyush/agentcontracts`:

- `main` branch protection requires one approving review.
- CODEOWNERS review is required.
- stale approving reviews are dismissed after new commits.
- conversations must be resolved before merge.
- linear history is required.
- force-pushes and branch deletion are disabled.
- branch protection is enforced for administrators.
- required status contexts are `test (3.9)`, `test (3.10)`,
  `test (3.11)`, `test (3.12)`, and `test (3.13)`.
- Dependabot vulnerability alerts and security updates are enabled.
- secret scanning and push protection are enabled.
- private vulnerability reporting is enabled.

Local registry context: `npm whoami` is `pyyush`, but this project publishes
the `aicontracts` package to PyPI. npm identity is not release authorization
evidence for this package.

## Known Blockers Before Final Release

- No `1.0.0` RC package, git tag, GitHub release, or artifact checksums have
  been cut or recorded.
- No external developer validation has been recorded.
- No GitHub Action RC run has been linked from an external repo.
- No GitHub Action RC run has installed and validated a real RC artifact yet.
- PyPI trusted publishing/provenance and release-owner authority still need
  confirmation before publishing.
- No remote GitHub Actions matrix run is linked for the current release commit
  across `test (3.9)`, `test (3.10)`, `test (3.11)`, `test (3.12)`, and
  `test (3.13)`.
- Final PyPI and GitHub releases must not happen until the external-user gate
  above is satisfied.

## Evidence Required For The Release DoD

Attach or link this evidence before marking Task 12 complete:

- RC artifact URLs and SHA256 hashes for wheel and sdist
- `python -m pip index versions aicontracts` output showing the RC or final
  package version as appropriate
- clean-project install output
- repo demo smoke output
- each external validation record
- each validator's `AGENT_CONTRACT.yaml`
- each validator's verdict artifact
- at least one GitHub Action run URL
- list of feedback items incorporated before final release
- list of feedback items deferred with owner and reason
