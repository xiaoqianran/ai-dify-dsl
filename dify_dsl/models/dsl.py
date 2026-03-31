"""Top-level DifyDSL model — the root of a parsed DSL file."""

from typing import Any, Dict, List
from pydantic import BaseModel, ConfigDict, model_validator

from dify_dsl.models.app import DifyApp, Dependency
from dify_dsl.models.workflow import Workflow
from dify_dsl.models.nodes import Node, parse_node


class DifyDSL(BaseModel):
    """Root model representing a complete Dify DSL file.

    Fields:
        app: Application metadata (name, mode, icon, etc.)
        dependencies: Marketplace/package dependencies
        kind: Always "app"
        version: DSL schema version (e.g. "0.1.5")
        workflow: The workflow definition with graph, features, variables
    """

    model_config = ConfigDict(extra="allow")

    app: DifyApp = DifyApp()
    dependencies: List[Dependency] = []
    kind: str = "app"
    version: str = "0.1.5"
    workflow: Workflow = Workflow()

    @model_validator(mode="before")
    @classmethod
    def _parse_graph_nodes(cls, values: Any) -> Any:
        """Convert raw node dicts into typed Node objects."""
        if isinstance(values, dict):
            workflow = values.get("workflow")
            if isinstance(workflow, dict):
                graph = workflow.get("graph")
                if isinstance(graph, dict):
                    raw_nodes = graph.get("nodes", [])
                    if raw_nodes and isinstance(raw_nodes[0], dict):
                        graph["nodes"] = [parse_node(n) for n in raw_nodes]
        return values

    # -- Convenience accessors --

    @property
    def nodes(self) -> List[Node]:
        """All nodes in the workflow graph."""
        return self.workflow.graph.nodes

    @property
    def edges(self) -> List:
        """All edges in the workflow graph."""
        return self.workflow.graph.edges

    def get_node(self, node_id: str) -> Node | None:
        """Find a node by its ID."""
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None

    def get_nodes_by_type(self, node_type: str) -> List[Node]:
        """Get all nodes of a specific type."""
        return [n for n in self.nodes if n.data.type == node_type]

    def node_type_counts(self) -> Dict[str, int]:
        """Count nodes grouped by type."""
        counts: Dict[str, int] = {}
        for node in self.nodes:
            t = node.data.type
            counts[t] = counts.get(t, 0) + 1
        return counts

    def summary(self) -> str:
        """Return a human-readable summary of the workflow."""
        lines = [
            f"Dify DSL: {self.app.name}",
            f"  Mode: {self.app.mode}",
            f"  Version: {self.version}",
            f"  Nodes: {len(self.nodes)}",
            f"  Edges: {len(self.edges)}",
        ]
        counts = self.node_type_counts()
        if counts:
            lines.append("  Node types:")
            for t, c in sorted(counts.items()):
                lines.append(f"    {t}: {c}")
        return "\n".join(lines)
