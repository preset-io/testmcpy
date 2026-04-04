"""
Evaluator Packs — versioned, reusable bundles of evaluators.

Usage in YAML:
  evaluators:
    - pack: "security-v1"
    - pack: "tool-basics"
    - name: response_includes  # Can mix packs with individual evaluators
      args:
        content: ["dashboard"]
"""

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# Built-in packs
BUILTIN_PACKS: dict[str, dict[str, Any]] = {
    "tool-basics": {
        "version": "1.0",
        "description": "Basic tool call validation",
        "evaluators": [
            {"name": "execution_successful"},
            {"name": "was_mcp_tool_called"},
        ],
    },
    "security-v1": {
        "version": "1.0",
        "description": "Security checks for MCP responses",
        "evaluators": [
            {"name": "no_leaked_data"},
            {
                "name": "response_not_includes",
                "args": {"content": ["Traceback", "stack trace", "Internal Server Error"]},
            },
            {"name": "no_hallucination"},
        ],
    },
    "chart-creation": {
        "version": "1.0",
        "description": "Chart creation validation",
        "evaluators": [
            {"name": "execution_successful"},
            {"name": "was_chart_created"},
            {"name": "url_is_valid"},
        ],
    },
    "sql-execution": {
        "version": "1.0",
        "description": "SQL execution validation",
        "evaluators": [
            {"name": "execution_successful"},
            {"name": "sql_query_valid"},
            {"name": "no_leaked_data"},
        ],
    },
    "response-quality": {
        "version": "1.0",
        "description": "Response quality checks",
        "evaluators": [
            {"name": "execution_successful"},
            {"name": "no_hallucination"},
        ],
    },
}

# Custom packs registered at runtime
_custom_packs: dict[str, dict[str, Any]] = {}


def resolve_evaluator_pack(pack_name: str) -> list[dict]:
    """Resolve a pack name to its list of evaluator configs.

    Looks up the pack in custom packs first, then built-in packs.

    Args:
        pack_name: Name of the evaluator pack to resolve.

    Returns:
        List of evaluator config dicts from the pack.

    Raises:
        ValueError: If the pack name is not found.
    """
    # Check custom packs first (allows overriding built-in packs)
    if pack_name in _custom_packs:
        pack = _custom_packs[pack_name]
        logger.debug(
            "Resolved pack '%s' from custom packs (v%s)", pack_name, pack.get("version", "?")
        )
        return list(pack["evaluators"])

    if pack_name in BUILTIN_PACKS:
        pack = BUILTIN_PACKS[pack_name]
        logger.debug(
            "Resolved pack '%s' from built-in packs (v%s)", pack_name, pack.get("version", "?")
        )
        return list(pack["evaluators"])

    available = sorted(set(list(BUILTIN_PACKS.keys()) + list(_custom_packs.keys())))
    raise ValueError(f"Unknown evaluator pack: '{pack_name}'. Available packs: {available}")


def list_packs() -> dict[str, dict[str, Any]]:
    """List all available packs with descriptions.

    Returns:
        Dict mapping pack name to pack info (version, description, evaluator count).
    """
    result: dict[str, dict[str, Any]] = {}
    # Built-in packs first
    for name, pack in BUILTIN_PACKS.items():
        result[name] = {
            "version": pack["version"],
            "description": pack["description"],
            "evaluator_count": len(pack["evaluators"]),
            "source": "builtin",
        }
    # Custom packs (may override built-in entries)
    for name, pack in _custom_packs.items():
        result[name] = {
            "version": pack.get("version", "1.0"),
            "description": pack.get("description", ""),
            "evaluator_count": len(pack["evaluators"]),
            "source": "custom",
        }
    return result


def register_custom_pack(
    name: str,
    evaluators: list[dict],
    version: str = "1.0",
    description: str = "",
) -> None:
    """Register a custom evaluator pack.

    Args:
        name: Unique name for the pack.
        evaluators: List of evaluator config dicts.
        version: Version string for the pack.
        description: Human-readable description.
    """
    _custom_packs[name] = {
        "version": version,
        "description": description,
        "evaluators": evaluators,
    }
    logger.info(
        "Registered custom evaluator pack '%s' (v%s) with %d evaluators",
        name,
        version,
        len(evaluators),
    )


def load_custom_packs_from_yaml(file_path: str | Path) -> int:
    """Load custom evaluator packs from a YAML file.

    Expected YAML format:
        packs:
          my-custom-pack:
            version: "1.0"
            description: "My custom evaluators"
            evaluators:
              - name: response_includes
                args: { content: ["success"] }
              - name: execution_successful

    Args:
        file_path: Path to the YAML file.

    Returns:
        Number of packs loaded.

    Raises:
        FileNotFoundError: If the file does not exist.
        yaml.YAMLError: If the file is not valid YAML.
        ValueError: If the YAML structure is invalid.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Evaluator packs file not found: {path}")

    with open(path) as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict) or "packs" not in data:
        raise ValueError(f"Invalid evaluator packs file: {path}. Expected top-level 'packs' key.")

    packs = data["packs"]
    if not isinstance(packs, dict):
        raise ValueError(f"Invalid evaluator packs file: {path}. 'packs' must be a mapping.")

    count = 0
    for pack_name, pack_config in packs.items():
        if not isinstance(pack_config, dict) or "evaluators" not in pack_config:
            logger.warning("Skipping invalid pack '%s': missing 'evaluators' key", pack_name)
            continue

        register_custom_pack(
            name=pack_name,
            evaluators=pack_config["evaluators"],
            version=pack_config.get("version", "1.0"),
            description=pack_config.get("description", ""),
        )
        count += 1

    logger.info("Loaded %d custom evaluator pack(s) from %s", count, path)
    return count


def resolve_evaluators(evaluator_configs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Resolve a list of evaluator configs, expanding any pack references.

    This is the main entry point for the test runner. It takes a mixed list
    of individual evaluator configs and pack references, and returns a flat
    list of individual evaluator configs.

    Args:
        evaluator_configs: List of evaluator configs, which may include
            pack references (dicts with a "pack" key).

    Returns:
        Flat list of individual evaluator configs with all packs expanded.
    """
    resolved: list[dict[str, Any]] = []
    for eval_config in evaluator_configs:
        if isinstance(eval_config, dict) and "pack" in eval_config:
            pack_evaluators = resolve_evaluator_pack(eval_config["pack"])
            resolved.extend(pack_evaluators)
        else:
            resolved.append(eval_config)
    return resolved
