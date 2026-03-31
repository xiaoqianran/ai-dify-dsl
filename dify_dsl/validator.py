"""Validate Dify DSL structure and node configurations.

Usage:
    from dify_dsl import parse_dsl
    from dify_dsl.validator import validate

    dsl = parse_dsl("workflow.yml")
    result = validate(dsl)
    if not result.is_valid:
        for error in result.errors:
            print(error)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Set

from dify_dsl.models.dsl import DifyDSL
from dify_dsl.models.nodes import (
    LLMNodeData,
    AgentNodeData,
    HttpRequestNodeData,
    Node,
)


@dataclass
class ValidationResult:
    """Result of DSL validation."""
    is_valid: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)
        self.is_valid = False

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)


def validate(dsl: DifyDSL) -> ValidationResult:
    """Run all validation checks on a parsed DSL.

    Checks:
        - Required top-level fields (app, kind, version, workflow)
        - Graph has nodes and edges
        - Start and end nodes exist
        - Node IDs are unique
        - Edge references point to existing nodes
        - No circular dependencies
        - Node-specific validation (LLM, Agent, HTTP)
    """
    result = ValidationResult()

    _validate_top_level(dsl, result)
    _validate_graph_structure(dsl, result)
    _validate_node_connections(dsl, result)
    _validate_node_configs(dsl, result)

    return result


def _validate_top_level(dsl: DifyDSL, result: ValidationResult) -> None:
    """Validate top-level DSL fields."""
    if not dsl.app.name:
        result.add_warning("App name is empty")
    if dsl.kind != "app":
        result.add_error(f"Expected kind='app', got '{dsl.kind}'")
    if not dsl.version:
        result.add_error("Missing DSL version")


def _validate_graph_structure(dsl: DifyDSL, result: ValidationResult) -> None:
    """Validate the workflow graph has proper structure."""
    nodes = dsl.nodes
    edges = dsl.edges

    if not nodes:
        result.add_error("Workflow has no nodes")
        return

    # Check start/end nodes
    node_types = {n.data.type for n in nodes}
    if "start" not in node_types:
        result.add_error("Workflow is missing a start node")
    if "end" not in node_types and "answer" not in node_types:
        result.add_warning("Workflow has no end or answer node")

    # Check ID uniqueness
    ids = [n.id for n in nodes]
    if len(ids) != len(set(ids)):
        seen: Set[str] = set()
        for nid in ids:
            if nid in seen:
                result.add_error(f"Duplicate node ID: {nid}")
            seen.add(nid)

    # Check edge references
    id_set = set(ids)
    for edge in edges:
        if edge.source not in id_set:
            result.add_error(f"Edge {edge.id} references missing source node {edge.source}")
        if edge.target not in id_set:
            result.add_error(f"Edge {edge.id} references missing target node {edge.target}")


def _validate_node_connections(dsl: DifyDSL, result: ValidationResult) -> None:
    """Validate node connection rules and detect cycles."""
    nodes = dsl.nodes
    edges = dsl.edges

    incoming: Dict[str, List[str]] = {n.id: [] for n in nodes}
    outgoing: Dict[str, List[str]] = {n.id: [] for n in nodes}

    for edge in edges:
        if edge.source in outgoing and edge.target in incoming:
            outgoing[edge.source].append(edge.target)
            incoming[edge.target].append(edge.source)

    for node in nodes:
        # Start nodes should have no incoming edges
        if node.data.type == "start" and incoming[node.id]:
            result.add_error(f"Start node {node.id} has incoming edges")
        # End nodes should have no outgoing edges
        if node.data.type == "end" and outgoing[node.id]:
            result.add_error(f"End node {node.id} has outgoing edges")

    # Cycle detection via DFS
    if _has_cycle(outgoing):
        result.add_error("Workflow graph contains a cycle")


def _has_cycle(adj: Dict[str, List[str]]) -> bool:
    """Detect cycles using iterative DFS with coloring."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {node: WHITE for node in adj}

    for start in adj:
        if color[start] != WHITE:
            continue
        stack = [(start, False)]
        while stack:
            node, backtrack = stack.pop()
            if backtrack:
                color[node] = BLACK
                continue
            if color[node] == GRAY:
                return True
            if color[node] == BLACK:
                continue
            color[node] = GRAY
            stack.append((node, True))  # backtrack marker
            for neighbor in adj.get(node, []):
                if color.get(neighbor) == GRAY:
                    return True
                if color.get(neighbor) == WHITE:
                    stack.append((neighbor, False))
    return False


def _validate_node_configs(dsl: DifyDSL, result: ValidationResult) -> None:
    """Validate individual node configurations."""
    for node in dsl.nodes:
        data = node.data

        if isinstance(data, LLMNodeData):
            _validate_llm(node, data, result)
        elif isinstance(data, AgentNodeData):
            _validate_agent(node, data, result)
        elif isinstance(data, HttpRequestNodeData):
            _validate_http(node, data, result)


def _validate_llm(node: Node, data: LLMNodeData, result: ValidationResult) -> None:
    """Validate LLM node configuration."""
    if not data.model:
        result.add_warning(f"LLM node {node.id} has no model configured")
    if not data.prompt_template:
        result.add_warning(f"LLM node {node.id} has no prompt template")


def _validate_agent(node: Node, data: AgentNodeData, result: ValidationResult) -> None:
    """Validate Agent node configuration."""
    if not data.agent_strategy_provider_name:
        result.add_warning(f"Agent node {node.id} has no strategy provider")
    if not data.agent_strategy_name:
        result.add_warning(f"Agent node {node.id} has no strategy name")


def _validate_http(node: Node, data: HttpRequestNodeData, result: ValidationResult) -> None:
    """Validate HTTP request node configuration."""
    if data.url and not (data.url.startswith("http://") or data.url.startswith("https://") or "{{" in data.url):
        result.add_warning(f"HTTP node {node.id} URL may be invalid: {data.url[:50]}")

    valid_methods = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}
    if data.method.upper() not in valid_methods:
        result.add_error(f"HTTP node {node.id} has invalid method: {data.method}")
