"""Framework adapters for Agent Contracts.

Each adapter is a thin wrapper (<200 LOC) that maps framework-specific
hooks to the SDK's enforcement API. Install the corresponding extra
to use an adapter:

    pip install agent-contracts[langchain]
    pip install agent-contracts[crewai]
    pip install agent-contracts[pydantic-ai]
"""
