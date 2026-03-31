"""Workflow analysis: topology, variable flow, and tool usage.

Usage:
    from dify_dsl import parse_dsl
    from dify_dsl.analyzer import analyze_topology, analyze_tools

    dsl = parse_dsl("workflow.yml")
    topo = analyze_topology(dsl)
    print(topo.summary)
"""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Set

from dify_dsl.models.dsl import DifyDSL
from dify_dsl.models.nodes import (
    LLMNodeData, CodeNodeData, AgentNodeData, ToolNodeData,
    McpServerNodeData, Node,
)


# ---------------------------------------------------------------------------
# Topology analysis
# ---------------------------------------------------------------------------

@dataclass
class TopologyResult:
    """Workflow graph topology analysis."""
    execution_levels: List[List[str]] = field(default_factory=list)
    unreachable_nodes: List[str] = field(default_factory=list)
    dead_end_nodes: List[str] = field(default_factory=list)
    parallelizable_groups: List[List[str]] = field(default_factory=list)

    @property
    def summary(self) -> str:
        lines = [f"Execution levels: {len(self.execution_levels)}"]
        for i, level in enumerate(self.execution_levels):
            lines.append(f"  Level {i}: {', '.join(level)}")
        if self.unreachable_nodes:
            lines.append(f"Unreachable nodes: {', '.join(self.unreachable_nodes)}")
        if self.dead_end_nodes:
            lines.append(f"Dead-end nodes (no outgoing): {', '.join(self.dead_end_nodes)}")
        if self.parallelizable_groups:
            lines.append(f"Parallelizable groups: {len(self.parallelizable_groups)}")
        return "\n".join(lines)


def analyze_topology(dsl: DifyDSL) -> TopologyResult:
    """Analyze the workflow graph topology.

    Performs:
    - Topological sort to determine execution levels
    - Detection of unreachable nodes (not connected to start)
    - Detection of dead-end nodes (no path to end)
    - Identification of parallelizable node groups
    """
    result = TopologyResult()
    nodes = dsl.nodes
    edges = dsl.edges

    if not nodes:
        return result

    # Build adjacency
    successors: Dict[str, List[str]] = defaultdict(list)
    predecessors: Dict[str, List[str]] = defaultdict(list)
    all_ids = {n.id for n in nodes}

    for edge in edges:
        if edge.source in all_ids and edge.target in all_ids:
            successors[edge.source].append(edge.target)
            predecessors[edge.target].append(edge.source)

    # Find start nodes
    start_ids = {n.id for n in nodes if n.data.type == "start"}
    end_ids = {n.id for n in nodes if n.data.type in ("end", "answer")}

    # BFS from start to find reachable nodes
    reachable: Set[str] = set()
    queue = list(start_ids)
    while queue:
        nid = queue.pop(0)
        if nid in reachable:
            continue
        reachable.add(nid)
        queue.extend(successors.get(nid, []))

    result.unreachable_nodes = [nid for nid in all_ids if nid not in reachable]

    # Reverse BFS from end to find nodes that can reach end
    reaches_end: Set[str] = set()
    queue = list(end_ids)
    while queue:
        nid = queue.pop(0)
        if nid in reaches_end:
            continue
        reaches_end.add(nid)
        queue.extend(predecessors.get(nid, []))

    result.dead_end_nodes = [
        nid for nid in all_ids
        if nid not in reaches_end and nid not in end_ids
        and nodes_by_id(nodes).get(nid, Node(id="", data=LLMNodeData())).data.type not in ("start",)
    ]

    # Topological sort (Kahn's algorithm)
    in_degree = {nid: 0 for nid in all_ids}
    for nid in all_ids:
        for succ in successors.get(nid, []):
            in_degree[succ] = in_degree.get(succ, 0) + 1

    current = [nid for nid in all_ids if in_degree[nid] == 0]
    while current:
        result.execution_levels.append(sorted(current))
        if len(current) > 1:
            result.parallelizable_groups.append(sorted(current))
        next_level = []
        for nid in current:
            for succ in successors.get(nid, []):
                in_degree[succ] -= 1
                if in_degree[succ] == 0:
                    next_level.append(succ)
        current = next_level

    return result


# ---------------------------------------------------------------------------
# Tool usage analysis
# ---------------------------------------------------------------------------

@dataclass
class ToolInfo:
    """Information about a tool used in the workflow."""
    node_id: str
    node_type: str
    tool_name: str = ""
    provider: str = ""
    enabled: bool = True


@dataclass
class ToolAnalysisResult:
    """Tool usage analysis results."""
    tools: List[ToolInfo] = field(default_factory=list)
    mcp_servers: List[ToolInfo] = field(default_factory=list)
    agent_tools: List[ToolInfo] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.tools) + len(self.mcp_servers) + len(self.agent_tools)

    @property
    def summary(self) -> str:
        lines = [f"Total tools: {self.total}"]
        if self.tools:
            lines.append(f"  Tool nodes: {len(self.tools)}")
            for t in self.tools:
                lines.append(f"    - {t.tool_name} ({t.provider})")
        if self.mcp_servers:
            lines.append(f"  MCP servers: {len(self.mcp_servers)}")
        if self.agent_tools:
            lines.append(f"  Agent tools: {len(self.agent_tools)}")
        return "\n".join(lines)


def analyze_tools(dsl: DifyDSL) -> ToolAnalysisResult:
    """Analyze tool usage across the workflow."""
    result = ToolAnalysisResult()

    for node in dsl.nodes:
        data = node.data
        if isinstance(data, ToolNodeData):
            result.tools.append(ToolInfo(
                node_id=node.id,
                node_type="tool",
                tool_name=data.tool_name,
                provider=data.provider_name,
            ))
        elif isinstance(data, McpServerNodeData):
            result.mcp_servers.append(ToolInfo(
                node_id=node.id,
                node_type="mcp-server",
                tool_name=f"MCP ({len(data.mcp_server_ids)} servers)",
            ))
        elif isinstance(data, AgentNodeData):
            agent_params = data.agent_parameters
            tools_list = agent_params.get("tools", [])
            if isinstance(tools_list, list):
                for t in tools_list:
                    if isinstance(t, dict) and t.get("enabled", False):
                        result.agent_tools.append(ToolInfo(
                            node_id=node.id,
                            node_type="agent",
                            tool_name=t.get("name", "unknown"),
                            enabled=t.get("enabled", True),
                        ))

    return result


# ---------------------------------------------------------------------------
# Variable flow analysis
# ---------------------------------------------------------------------------

@dataclass
class VariableFlowResult:
    """Variable flow analysis across the workflow."""
    # node_id -> list of variable references it reads
    reads: Dict[str, List[str]] = field(default_factory=dict)
    # node_id -> list of variable names it writes
    writes: Dict[str, List[str]] = field(default_factory=dict)

    @property
    def summary(self) -> str:
        lines = ["Variable flow:"]
        all_nodes = set(self.reads) | set(self.writes)
        for nid in sorted(all_nodes):
            w = self.writes.get(nid, [])
            r = self.reads.get(nid, [])
            parts = []
            if w:
                parts.append(f"writes: {', '.join(w)}")
            if r:
                parts.append(f"reads: {', '.join(r[:5])}")
            if parts:
                lines.append(f"  {nid}: {'; '.join(parts)}")
        return "\n".join(lines)


def analyze_variable_flow(dsl: DifyDSL) -> VariableFlowResult:
    """Analyze variable reads/writes across nodes.

    This is a best-effort static analysis that looks for variable
    reference patterns like ``{{#node_id.field#}}`` in node configs.
    """
    import re

    result = VariableFlowResult()
    var_ref_pattern = re.compile(r"\{\{#([^#]+)#\}\}")

    for node in dsl.nodes:
        data_dict = node.data.model_dump()
        node_id = node.id

        # Collect all string values to find variable references
        refs: List[str] = []
        _collect_var_refs(data_dict, var_ref_pattern, refs)
        if refs:
            result.reads[node_id] = refs

        # Nodes that produce outputs
        if isinstance(node.data, CodeNodeData) and node.data.outputs:
            result.writes[node_id] = list(node.data.outputs.keys())
        elif node.data.type == "start":
            # Start node variables
            vars_list = getattr(node.data, "variables", [])
            if isinstance(vars_list, list):
                result.writes[node_id] = [
                    v.get("variable", v.get("label", ""))
                    for v in vars_list if isinstance(v, dict)
                ]

    return result


def _collect_var_refs(obj: Any, pattern: Any, refs: List[str]) -> None:
    """Recursively collect variable references from nested data."""
    if isinstance(obj, str):
        matches = pattern.findall(obj)
        refs.extend(matches)
    elif isinstance(obj, dict):
        for v in obj.values():
            _collect_var_refs(v, pattern, refs)
    elif isinstance(obj, list):
        for item in obj:
            _collect_var_refs(item, pattern, refs)


def nodes_by_id(nodes: List[Node]) -> Dict[str, Node]:
    """Build a node lookup dict."""
    return {n.id: n for n in nodes}
