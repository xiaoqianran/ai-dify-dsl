"""Generate Dify DSL YAML from typed models.

Usage:
    generate_dsl(dsl, "output.yml")
    yaml_str = generate_dsl_string(dsl)
"""

from pathlib import Path
from typing import Any, Dict, List, Union

from pydantic import BaseModel

from dify_dsl.models.dsl import DifyDSL

# Prefer ruamel.yaml for format-preserving output
try:
    from ruamel.yaml import YAML as _RuamelYAML
    from ruamel.yaml.comments import CommentedMap, CommentedSeq

    def _dump_yaml(data: Dict[str, Any], path: Union[str, Path]) -> None:
        ry = _RuamelYAML()
        ry.preserve_quotes = True
        ry.width = 4096
        ry.default_flow_style = False
        with open(path, "w", encoding="utf-8") as f:
            ry.dump(_to_ruamel(data), f)

    def _dump_yaml_string(data: Dict[str, Any]) -> str:
        ry = _RuamelYAML()
        ry.preserve_quotes = True
        ry.width = 4096
        ry.default_flow_style = False
        from io import StringIO
        buf = StringIO()
        ry.dump(_to_ruamel(data), buf)
        return buf.getvalue()

    def _to_ruamel(obj: Any) -> Any:
        """Convert plain dicts/lists to ruamel types for proper formatting."""
        if isinstance(obj, dict):
            cm = CommentedMap()
            for k, v in obj.items():
                cm[k] = _to_ruamel(v)
            return cm
        elif isinstance(obj, list):
            cs = CommentedSeq()
            for item in obj:
                cs.append(_to_ruamel(item))
            return cs
        return obj

    RUAMEL_AVAILABLE = True

except ImportError:
    import yaml as _pyyaml

    def _dump_yaml(data: Dict[str, Any], path: Union[str, Path]) -> None:
        with open(path, "w", encoding="utf-8") as f:
            _pyyaml.dump(data, f, default_flow_style=False, allow_unicode=True,
                         sort_keys=False)

    def _dump_yaml_string(data: Dict[str, Any]) -> str:
        return _pyyaml.dump(data, default_flow_style=False, allow_unicode=True,
                            sort_keys=False)

    RUAMEL_AVAILABLE = False


def _model_to_dict(obj: Any) -> Any:
    """Recursively convert Pydantic models to plain dicts.

    Preserves field ordering and extra fields from ``extra='allow'``.
    """
    if isinstance(obj, BaseModel):
        # model_dump preserves extra fields and field order
        d = obj.model_dump(mode="python", exclude_none=False)
        # Recursively convert any nested models that model_dump may have missed
        return _model_to_dict(d)
    elif isinstance(obj, dict):
        return {k: _model_to_dict(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_model_to_dict(item) for item in obj]
    return obj


def generate_dsl(dsl: DifyDSL, path: Union[str, Path]) -> None:
    """Generate a Dify DSL YAML file from a typed model.

    Args:
        dsl: The DifyDSL model to serialize.
        path: Output file path.
    """
    data = _model_to_dict(dsl)
    _dump_yaml(data, path)


def generate_dsl_string(dsl: DifyDSL) -> str:
    """Generate a Dify DSL YAML string from a typed model.

    Args:
        dsl: The DifyDSL model to serialize.

    Returns:
        YAML string.
    """
    data = _model_to_dict(dsl)
    return _dump_yaml_string(data)
