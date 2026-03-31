"""Split a Dify DSL into modular, editable files.

Usage:
    from dify_dsl import parse_dsl
    from dify_dsl.splitter import split_workflow

    dsl = parse_dsl("workflow.yml")
    split_workflow(dsl, "output_dir/")
"""

import json
from pathlib import Path
from typing import Any, Dict

from dify_dsl.models.dsl import DifyDSL
from dify_dsl.models.nodes import (
    LLMNodeData,
    CodeNodeData,
    AgentNodeData,
    ToolNodeData,
    HttpRequestNodeData,
    IfElseNodeData,
    IterationNodeData,
    TemplateTransformNodeData,
    McpServerNodeData,
    Node,
    PromptItem,
)

# Prefer ruamel.yaml
try:
    from ruamel.yaml import YAML as _RuamelYAML

    def _dump_yaml(data: Any, path: Path) -> None:
        ry = _RuamelYAML()
        ry.preserve_quotes = True
        ry.width = 4096
        ry.default_flow_style = False
        with open(path, "w", encoding="utf-8") as f:
            ry.dump(data, f)

except ImportError:
    import yaml as _pyyaml

    def _dump_yaml(data: Any, path: Path) -> None:
        with open(path, "w", encoding="utf-8") as f:
            _pyyaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


_CODE_EXT = {
    "python3": "py", "python": "py",
    "javascript": "js", "typescript": "ts",
}


def split_workflow(dsl: DifyDSL, output_dir: str | Path) -> Path:
    """Split a parsed DSL into modular files for local editing.

    Creates:
        output_dir/
        ├── metadata/
        │   ├── workflow_info.json
        │   ├── edges.json
        │   └── features.json
        └── nodes/
            ├── <type>/
            │   └── <id>/
            │       ├── config.yaml
            │       ├── metadata.json
            │       └── (type-specific files)

    Returns:
        The output directory path.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # Metadata
    meta_dir = out / "metadata"
    meta_dir.mkdir(exist_ok=True)

    _save_json(meta_dir / "workflow_info.json", {
        "app": dsl.app.model_dump(),
        "dependencies": [d.model_dump() for d in dsl.dependencies],
        "kind": dsl.kind,
        "version": dsl.version,
        "conversation_variables": dsl.workflow.conversation_variables,
        "environment_variables": dsl.workflow.environment_variables,
    })

    _save_json(meta_dir / "edges.json", [e.model_dump() for e in dsl.edges])
    _save_json(meta_dir / "features.json", dsl.workflow.features.model_dump())

    # Nodes
    nodes_dir = out / "nodes"
    nodes_dir.mkdir(exist_ok=True)

    type_counter: Dict[str, int] = {}
    node_index: Dict[str, Dict[str, str]] = {}

    for node in dsl.nodes:
        ntype = node.data.type
        type_counter[ntype] = type_counter.get(ntype, 0) + 1
        idx = type_counter[ntype]

        # Each node gets its own directory: nodes/<type>/<idx>_<id>/
        node_dir_name = f"{idx:02d}_{node.id}"
        node_dir = nodes_dir / ntype / node_dir_name
        node_dir.mkdir(parents=True, exist_ok=True)

        _split_node(node, node_dir)

        node_index[node.id] = {
            "type": ntype,
            "path": str(node_dir.relative_to(out)),
            "title": node.data.title,
        }

    _save_json(meta_dir / "node_index.json", node_index)

    # Summary
    _save_json(out / "summary.json", {
        "app_name": dsl.app.name,
        "version": dsl.version,
        "total_nodes": len(dsl.nodes),
        "total_edges": len(dsl.edges),
        "node_types": dsl.node_type_counts(),
    })

    return out


def _split_node(node: Node, node_dir: Path) -> None:
    """Split a single node into editable files."""
    data = node.data

    # Common metadata for all node types
    node_meta = {
        "node_id": node.id,
        "type": data.type,
        "title": data.title,
        "position": node.position,
        "width": node.width,
        "height": node.height,
    }
    # Preserve extra node-level fields
    for k in ("parentId", "extent", "zIndex"):
        v = getattr(node, k, None)
        if v is not None:
            node_meta[k] = v

    _save_json(node_dir / "metadata.json", node_meta)

    # Type-specific splitting
    if isinstance(data, LLMNodeData):
        _split_llm(data, node_dir)
    elif isinstance(data, CodeNodeData):
        _split_code(data, node_dir)
    elif isinstance(data, AgentNodeData):
        _split_agent(data, node_dir)
    elif isinstance(data, ToolNodeData):
        _split_tool(data, node_dir)
    elif isinstance(data, HttpRequestNodeData):
        _split_http(data, node_dir)
    elif isinstance(data, IfElseNodeData):
        _split_if_else(data, node_dir)
    elif isinstance(data, IterationNodeData):
        _split_iteration(data, node_dir)
    elif isinstance(data, TemplateTransformNodeData):
        _split_template(data, node_dir)
    elif isinstance(data, McpServerNodeData):
        _split_mcp(data, node_dir)
    else:
        # Generic: dump full data as config
        _dump_yaml(data.model_dump(), node_dir / "config.yaml")


def _split_llm(data: LLMNodeData, d: Path) -> None:
    """Split LLM node: separate prompts from config."""
    config = data.model_dump()
    prompts = config.pop("prompt_template", [])
    _dump_yaml(config, d / "config.yaml")

    for i, prompt in enumerate(prompts):
        role = prompt.get("role", "user")
        text = prompt.get("text", "")
        (d / f"{role}_prompt_{i + 1}.txt").write_text(text, encoding="utf-8")

    _save_json(d / "prompts_meta.json", [
        {k: v for k, v in p.items() if k != "text"} for p in prompts
    ])


def _split_code(data: CodeNodeData, d: Path) -> None:
    """Split Code node: separate code from config."""
    config = data.model_dump()
    code = config.pop("code", "")
    lang = data.code_language
    ext = _CODE_EXT.get(lang, "txt")
    _dump_yaml(config, d / "config.yaml")
    (d / f"code.{ext}").write_text(code, encoding="utf-8")


def _split_agent(data: AgentNodeData, d: Path) -> None:
    """Split Agent node: separate prompts and parameters."""
    config = data.model_dump()
    prompts = config.pop("prompt_template", [])
    params = config.pop("agent_parameters", {})
    _dump_yaml(config, d / "config.yaml")

    if params:
        _dump_yaml(params, d / "agent_parameters.yaml")

    for i, prompt in enumerate(prompts):
        role = prompt.get("role", "user")
        text = prompt.get("text", "")
        (d / f"{role}_prompt_{i + 1}.txt").write_text(text, encoding="utf-8")

    _save_json(d / "prompts_meta.json", [
        {k: v for k, v in p.items() if k != "text"} for p in prompts
    ])


def _split_tool(data: ToolNodeData, d: Path) -> None:
    """Split Tool node: separate tool config."""
    config = data.model_dump()
    tool_params = config.pop("tool_parameters", {})
    tool_configs = config.pop("tool_configurations", {})
    _dump_yaml(config, d / "config.yaml")
    _dump_yaml({"tool_parameters": tool_params, "tool_configurations": tool_configs},
               d / "tool_config.yaml")


def _split_http(data: HttpRequestNodeData, d: Path) -> None:
    """Split HTTP node: separate request details."""
    config = data.model_dump()
    http_parts = {}
    for key in ("headers", "params", "body", "authorization"):
        http_parts[key] = config.pop(key, None)
    _dump_yaml(config, d / "config.yaml")
    _dump_yaml(http_parts, d / "http_config.yaml")


def _split_if_else(data: IfElseNodeData, d: Path) -> None:
    """Split IfElse node: separate conditions."""
    config = data.model_dump()
    conditions = config.pop("conditions", [])
    _dump_yaml(config, d / "config.yaml")
    _save_json(d / "conditions.json", conditions)


def _split_iteration(data: IterationNodeData, d: Path) -> None:
    """Split Iteration node."""
    _dump_yaml(data.model_dump(), d / "config.yaml")


def _split_template(data: TemplateTransformNodeData, d: Path) -> None:
    """Split Template node: separate template text."""
    config = data.model_dump()
    template = config.pop("template", "")
    _dump_yaml(config, d / "config.yaml")
    (d / "template.txt").write_text(template, encoding="utf-8")


def _split_mcp(data: McpServerNodeData, d: Path) -> None:
    """Split MCP server node."""
    _dump_yaml(data.model_dump(), d / "config.yaml")


def _save_json(path: Path, data: Any) -> None:
    """Write JSON with proper encoding."""
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
