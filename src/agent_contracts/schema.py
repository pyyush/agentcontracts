"""JSON Schema loading and validation for Agent Contract YAML files."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

import jsonschema

_SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"
_CONTRACT_SCHEMA_FILE = _SCHEMA_DIR / "agent-contract.schema.json"
_VERDICT_SCHEMA_FILE = _SCHEMA_DIR / "verdict.schema.json"


@lru_cache(maxsize=1)
def get_schema() -> Dict[str, Any]:
    """Load and cache the Agent Contract JSON Schema."""
    with open(_CONTRACT_SCHEMA_FILE, encoding="utf-8") as f:
        return json.load(f)  # type: ignore[no-any-return]


@lru_cache(maxsize=1)
def get_verdict_schema() -> Dict[str, Any]:
    """Load and cache the verdict artifact JSON Schema."""
    with open(_VERDICT_SCHEMA_FILE, encoding="utf-8") as f:
        return json.load(f)  # type: ignore[no-any-return]


def validate_against_schema(data: Dict[str, Any]) -> List[str]:
    """Validate a parsed YAML dict against the Agent Contract JSON Schema.

    Returns a list of validation error messages. Empty list means valid.
    """
    schema = get_schema()
    validator = jsonschema.Draft202012Validator(schema)
    errors: List[str] = []
    for error in sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path)):
        path = ".".join(str(p) for p in error.absolute_path) or "(root)"
        errors.append(f"{path}: {error.message}")
    return errors


def validate_verdict_against_schema(data: Any) -> List[str]:
    """Validate a verdict artifact dict against the verdict JSON Schema.

    Returns a list of validation error messages. Empty list means valid.
    """
    schema = get_verdict_schema()
    validator = jsonschema.Draft202012Validator(schema)
    errors: List[str] = []
    for error in sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path)):
        path = ".".join(str(p) for p in error.absolute_path) or "(root)"
        errors.append(f"{path}: {error.message}")
    return errors
