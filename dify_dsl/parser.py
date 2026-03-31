"""Parse Dify DSL YAML files into typed models.

Usage:
    dsl = parse_dsl("workflow.yml")
    dsl = parse_dsl_string(yaml_string)
"""

from pathlib import Path
from typing import Any, Dict, Union

from dify_dsl.models.dsl import DifyDSL

# Prefer ruamel.yaml for format-preserving round-trip
try:
    from ruamel.yaml import YAML as _RuamelYAML

    def _load_yaml(source: Union[str, Path]) -> Dict[str, Any]:
        ry = _RuamelYAML()
        ry.preserve_quotes = True
        with open(source, "r", encoding="utf-8") as f:
            data = ry.load(f)
        return _ruamel_to_dict(data)

    def _load_yaml_string(text: str) -> Dict[str, Any]:
        ry = _RuamelYAML()
        ry.preserve_quotes = True
        from io import StringIO
        data = ry.load(StringIO(text))
        return _ruamel_to_dict(data)

    def _ruamel_to_dict(obj: Any) -> Any:
        """Recursively convert ruamel.yaml objects to plain dicts/lists."""
        from ruamel.yaml.comments import CommentedMap, CommentedSeq
        if isinstance(obj, CommentedMap):
            return {str(k): _ruamel_to_dict(v) for k, v in obj.items()}
        elif isinstance(obj, CommentedSeq):
            return [_ruamel_to_dict(item) for item in obj]
        return obj

    RUAMEL_AVAILABLE = True

except ImportError:
    import yaml as _pyyaml

    def _load_yaml(source: Union[str, Path]) -> Dict[str, Any]:
        with open(source, "r", encoding="utf-8") as f:
            return _pyyaml.safe_load(f) or {}

    def _load_yaml_string(text: str) -> Dict[str, Any]:
        return _pyyaml.safe_load(text) or {}

    RUAMEL_AVAILABLE = False


def parse_dsl(path: Union[str, Path]) -> DifyDSL:
    """Parse a Dify DSL YAML file into a typed ``DifyDSL`` model.

    Args:
        path: Path to the YAML file.

    Returns:
        A fully typed DifyDSL object.
    """
    raw = _load_yaml(path)
    return DifyDSL.model_validate(raw)


def parse_dsl_string(text: str) -> DifyDSL:
    """Parse a Dify DSL YAML string into a typed ``DifyDSL`` model.

    Args:
        text: YAML string content.

    Returns:
        A fully typed DifyDSL object.
    """
    raw = _load_yaml_string(text)
    return DifyDSL.model_validate(raw)
