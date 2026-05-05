"""Framework adapters for Agent Contracts.

The contract, CLI, verdict artifact, and GitHub Action are framework-
agnostic by design — these adapters are optional ergonomic helpers that
forward in-runtime hook calls into the same enforcer. The CI verdict
gate is the source of truth.

    pip install aicontracts[claude]       # Python 3.10+
    pip install aicontracts[openai]
    pip install aicontracts[langchain]
"""

from agent_contracts.adapters._shared import AdapterVerdictError

__all__ = ["AdapterVerdictError"]
