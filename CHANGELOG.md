# Changelog

All notable changes to this project are tracked here.

## [0.2.0] - 2026-04-06

### Added

- repo-local coding/build-agent positioning across the README, spec, examples, and canonical contract
- filesystem read/write authorization scopes
- shell command authorization scopes
- shell-command budgets
- verdict artifact emission and CLI verdict gating
- coding-agent trace bootstrap improvements
- coding/build-focused demo contracts and CI action semantics
- real-SDK integration tests for Claude, OpenAI, and LangChain adapters (run against the pinned SDK versions in CI)

### Changed

- positioned the contract + CLI + verdict artifact + GitHub Action as the framework-agnostic, provider-agnostic enforcement surface; the CI verdict gate is the source of truth
- pinned framework adapter SDKs to exact versions: `claude-agent-sdk==0.1.56`, `openai-agents==0.13.5`, `langchain-core==1.2.26`
- gated all three adapter extras on Python 3.10+ (core remains 3.9+)
- fixed the OpenAI adapter import path (`from agents import RunHooks`)

### Removed

- CrewAI adapter and `[crewai]` extra
- Pydantic AI adapter and `[pydantic-ai]` extra
