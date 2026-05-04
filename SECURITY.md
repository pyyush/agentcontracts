# Security Policy

## Supported Versions

Security fixes are prepared for the latest published `0.x` release and the
planned `1.0.0` release line until `1.0.0` is published.

## Reporting A Vulnerability

Use GitHub's private vulnerability reporting or Security Advisory flow for
sensitive reports. If private reporting is not available, open a public GitHub
issue only for non-sensitive security hardening requests.

Please include:

- affected package version and install source
- the contract file or verdict artifact shape involved, with secrets removed
- steps to reproduce
- expected impact
- whether the issue affects the CLI, Python API, GitHub Action, schemas, or an adapter

Do not include secrets, private repository contents, customer data, or live
credentials in a public issue.

## Response Expectations

Reports that can lead to policy bypass, unsafe file/shell/network access,
fake-green verdicts, or credential exposure are treated as release blockers.
The maintainer will acknowledge actionable reports in the advisory or issue
thread and will publish fixes with changelog and migration notes when needed.
