"""Rebuild a Dify DSL from split files.

Usage:
    from dify_dsl.rebuilder import rebuild_workflow
    from dify_dsl.generator import generate_dsl

    dsl = rebuild_workflow("split_output_dir/")
    generate_dsl(dsl, "rebuilt.yml")
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from dify_dsl.models.dsl import DifyDSL
from dify_dsl.models.app import DifyApp, Dependency
from dify_dsl.models.workflow import Workflow, Features, Graph, Edge
from dify_dsl.models.nodes import Node, parse_node, parse_node_data

# Prefer ruamel.yaml
try:
    from ruamel.yaml import YAML as _RuamelYAML
    from ruamel.yaml.comments import CommentedMap, CommentedSeq

    def _load_yaml(path: Path) -> Any:
        ry = _RuamelYAML()
        ry.preserve_quotes = True
        with open(path, "r", encoding="utf-8") as f:
            data = ry.load(f)
        return _to_plain(data)

    def _to_plain(obj: Any) -> Any:
        if isinstance(obj, CommentedMap):
            return {str(k): _to_plain(v) for k, v in obj.items()}
        elif isinstance(obj, CommentedSeq):
            return [_to_plain(i) for i in obj]
        return obj

except ImportError:
    import yaml as _pyyaml

    def _load_yaml(path: Path) -> Any:
        with open(path, "r", encoding="utf-8") as f:
            return _pyyaml.safe_load(f)


_CODE_EXT = {
    "python3": "py", "python": "py",
    "javascript": "js", "typescript": "ts",
}


def rebuild_workflow(split_dir: str | Path) -> DifyDSL:
    """Rebuild a DifyDSL model from a split directory.

    Args:
        split_dir: Path to the directory created by ``split_workflow``.

    Returns:
        A fully typed DifyDSL object ready for generation.
    """
    root = Path(split_dir)

    # Load metadata
    workflow_info = _load_json(root / "metadata" / "workflow_info.json")
    edges_raw = _load_json(root / "metadata" / "edges.json")
    features_raw = _load_json(root / "metadata" / "features.json")
    node_index = _load_json(root / "metadata" / "node_index.json")

    # Rebuild nodes
    nodes: List[Node] = []
    for node_id, info in node_index.items():
        node_path = root / info["path"]
        node = _rebuild_node(node_id, info["type"], node_path)
        if node:
            nodes.append(node)

    # 新格式保存原始键集合与未知字段，避免重建时补入默认值或丢失扩展字段。
    if "root_fields" in workflow_info:
        root_data = dict(workflow_info["root_fields"])
        workflow_data = dict(workflow_info["workflow_fields"])
        workflow_data["features"] = features_raw
        workflow_data["graph"] = {
            **workflow_info.get("graph_fields", {}),
            "nodes": [node.model_dump(mode="python", serialize_as_any=True, exclude_unset=True) for node in nodes],
            "edges": edges_raw,
        }
        root_data["workflow"] = workflow_data
        return DifyDSL.model_validate(root_data)

    # 兼容历史拆分目录（未记录原始字段集合）。
    dsl = DifyDSL(
        app=DifyApp.model_validate(workflow_info.get("app", {})),
        dependencies=[Dependency.model_validate(d) for d in workflow_info.get("dependencies", [])],
        kind=workflow_info.get("kind", "app"),
        version=workflow_info.get("version", "0.1.5"),
        workflow=Workflow(
            conversation_variables=workflow_info.get("conversation_variables", []),
            environment_variables=workflow_info.get("environment_variables", []),
            features=Features.model_validate(features_raw),
            graph=Graph(
                nodes=nodes,
                edges=[Edge.model_validate(e) for e in edges_raw],
            ),
        ),
    )

    return dsl


def _rebuild_node(node_id: str, node_type: str, node_dir: Path) -> Optional[Node]:
    """Rebuild a single node from its split files."""
    meta_path = node_dir / "metadata.json"
    if not meta_path.exists():
        return None

    meta = _load_json(meta_path)

    # Load base config
    config_path = node_dir / "config.yaml"
    if config_path.exists():
        config = _load_yaml(config_path) or {}
    else:
        config = {}

    # Ensure type is set
    config["type"] = node_type

    # Type-specific reconstruction
    if node_type == "llm":
        config = _rebuild_llm(config, node_dir)
    elif node_type == "code":
        config = _rebuild_code(config, node_dir)
    elif node_type == "agent":
        config = _rebuild_agent(config, node_dir)
    elif node_type == "tool":
        config = _rebuild_tool(config, node_dir)
    elif node_type in ("http_request", "http-request"):
        config = _rebuild_http(config, node_dir)
    elif node_type in ("if_else", "if-else"):
        config = _rebuild_if_else(config, node_dir)
    elif node_type == "template_transform":
        config = _rebuild_template(config, node_dir)

    # 只保留原本显式设置的字段，避免凭空增加未使用的默认配置。
    if "explicit_data_fields" in meta:
        config = {k: v for k, v in config.items() if k in meta["explicit_data_fields"]}
    if "node_fields" in meta:
        return parse_node({**meta["node_fields"], "data": config})

    # 兼容历史拆分目录。
    typed_data = parse_node_data(config)
    return Node(
        id=node_id,
        data=typed_data,
        position=meta.get("position", {}),
        width=meta.get("width"),
        height=meta.get("height"),
        type="custom",
        sourcePosition="right",
        targetPosition="left",
        parentId=meta.get("parentId"),
        extent=meta.get("extent"),
        zIndex=meta.get("zIndex", 0),
    )


def _rebuild_llm(config: Dict, d: Path) -> Dict:
    """Rebuild LLM node: merge prompts back."""
    prompts_meta_path = d / "prompts_meta.json"
    if prompts_meta_path.exists():
        prompts_meta = _load_json(prompts_meta_path)
        prompts = []
        for i, pm in enumerate(prompts_meta):
            role = pm.get("role", "user")
            text_file = d / f"{role}_prompt_{i + 1}.txt"
            text = text_file.read_text(encoding="utf-8") if text_file.exists() else ""
            prompts.append({**pm, "text": text})
        config["prompt_template"] = prompts
    return config


def _rebuild_code(config: Dict, d: Path) -> Dict:
    """Rebuild Code node: merge code back."""
    lang = config.get("code_language", "python3")
    ext = _CODE_EXT.get(lang, "txt")
    code_file = d / f"code.{ext}"
    if code_file.exists():
        config["code"] = code_file.read_text(encoding="utf-8")
    return config


def _rebuild_agent(config: Dict, d: Path) -> Dict:
    """Rebuild Agent node: merge prompts and parameters."""
    # Parameters
    params_file = d / "agent_parameters.yaml"
    if params_file.exists():
        config["agent_parameters"] = _load_yaml(params_file) or {}

    # Prompts
    prompts_meta_path = d / "prompts_meta.json"
    if prompts_meta_path.exists():
        prompts_meta = _load_json(prompts_meta_path)
        prompts = []
        for i, pm in enumerate(prompts_meta):
            role = pm.get("role", "user")
            text_file = d / f"{role}_prompt_{i + 1}.txt"
            text = text_file.read_text(encoding="utf-8") if text_file.exists() else ""
            prompts.append({**pm, "text": text})
        config["prompt_template"] = prompts

    return config


def _rebuild_tool(config: Dict, d: Path) -> Dict:
    """Rebuild Tool node: merge tool config."""
    tool_config_path = d / "tool_config.yaml"
    if tool_config_path.exists():
        tc = _load_yaml(tool_config_path) or {}
        config.update(tc)
    return config


def _rebuild_http(config: Dict, d: Path) -> Dict:
    """Rebuild HTTP node: merge request details."""
    http_config_path = d / "http_config.yaml"
    if http_config_path.exists():
        hc = _load_yaml(http_config_path) or {}
        config.update(hc)
    return config


def _rebuild_if_else(config: Dict, d: Path) -> Dict:
    """Rebuild IfElse node: merge conditions."""
    conditions_path = d / "conditions.json"
    if conditions_path.exists():
        config["conditions"] = _load_json(conditions_path)
    return config


def _rebuild_template(config: Dict, d: Path) -> Dict:
    """Rebuild Template node: merge template text."""
    template_path = d / "template.txt"
    if template_path.exists():
        config["template"] = template_path.read_text(encoding="utf-8")
    return config


def _load_json(path: Path) -> Any:
    """Load a JSON file."""
    return json.loads(path.read_text(encoding="utf-8"))
