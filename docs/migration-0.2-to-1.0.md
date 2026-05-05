# Migration Notes: `aicontracts 0.2.0` To `1.0.0`

`1.0.0` is the first stable release train. The package is not published until PyPI has `aicontracts==1.0.0` and the GitHub tag `v1.0.0` exists.

## Required Changes

1. Change `agent_contract` to `"1.0.0"` in stable contracts.
2. If `effects.authorized` is present, explicitly list every effect sub-surface you intend to allow. Omitted `filesystem` and `shell` sub-surfaces now deny file and shell effects by default.
3. Review every `filesystem.read` and `filesystem.write` pattern. Paths are canonicalized before matching, so traversal-shaped inputs such as `src/../.env` no longer match `src/**`.
4. Replace placeholder `eval:` blocking postconditions with deterministic checks or a real evaluator integration. A `sync_block` `eval:` check without an evaluator fails closed.
5. Gate schema-backed verdict artifacts with `aicontracts check-verdict`; malformed artifacts now fail before outcome evaluation.

## Optional Changes

- Update LangChain installs to the fixed `langchain-core==1.2.28` pin through `aicontracts[langchain]`.
- Add required repo checks with `ContractEnforcer.record_check(...)` so the final verdict can distinguish policy blocks from red tests.
- Regenerate docs with `python scripts/generate_api_reference.py` before publishing docs.
- Use the examples in `examples/` as acceptance tests for local adoption demos.

## Compatibility Notes

Stable SemVer covers the public Python imports in `agent_contracts.__all__`, CLI command names and exit semantics, the contract schema, the verdict schema, and the GitHub Action inputs/outputs.

The optional SDK adapters remain thin host integrations. Their limits are documented in `docs/adoption-guide.md`; the CI verdict gate remains the complete enforcement path for hosts that do not expose pre-execution effect hooks.
