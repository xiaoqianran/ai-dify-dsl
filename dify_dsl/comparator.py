"""Compare two Dify DSL files or models.

Usage:
    from dify_dsl.comparator import compare_dsl, compare_files

    result = compare_files("original.yml", "modified.yml")
    print(result.summary)
"""

import difflib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

from dify_dsl.models.dsl import DifyDSL


@dataclass
class NodeDiff:
    """A difference detected in a specific node."""
    node_id: str
    node_type: str
    change_type: str  # "added" | "removed" | "modified"
    details: str = ""


@dataclass
class CompareResult:
    """Result of comparing two DSL structures."""
    nodes_added: List[NodeDiff] = field(default_factory=list)
    nodes_removed: List[NodeDiff] = field(default_factory=list)
    nodes_modified: List[NodeDiff] = field(default_factory=list)
    edges_added: int = 0
    edges_removed: int = 0
    text_diff: str = ""

    @property
    def has_changes(self) -> bool:
        return bool(self.nodes_added or self.nodes_removed or self.nodes_modified
                     or self.edges_added or self.edges_removed)

    @property
    def summary(self) -> str:
        lines = []
        if self.nodes_added:
            lines.append(f"Nodes added: {len(self.nodes_added)}")
            for n in self.nodes_added:
                lines.append(f"  + {n.node_type}/{n.node_id}")
        if self.nodes_removed:
            lines.append(f"Nodes removed: {len(self.nodes_removed)}")
            for n in self.nodes_removed:
                lines.append(f"  - {n.node_type}/{n.node_id}")
        if self.nodes_modified:
            lines.append(f"Nodes modified: {len(self.nodes_modified)}")
            for n in self.nodes_modified:
                lines.append(f"  ~ {n.node_type}/{n.node_id}: {n.details}")
        if self.edges_added:
            lines.append(f"Edges added: {self.edges_added}")
        if self.edges_removed:
            lines.append(f"Edges removed: {self.edges_removed}")
        if not lines:
            lines.append("No changes detected")
        return "\n".join(lines)


def compare_dsl(original: DifyDSL, modified: DifyDSL) -> CompareResult:
    """Compare two parsed DSL models.

    Returns:
        A CompareResult with structural differences.
    """
    result = CompareResult()

    # Compare nodes
    orig_ids = {n.id: n for n in original.nodes}
    mod_ids = {n.id: n for n in modified.nodes}

    orig_set = set(orig_ids.keys())
    mod_set = set(mod_ids.keys())

    for nid in mod_set - orig_set:
        n = mod_ids[nid]
        result.nodes_added.append(NodeDiff(nid, n.data.type, "added"))

    for nid in orig_set - mod_set:
        n = orig_ids[nid]
        result.nodes_removed.append(NodeDiff(nid, n.data.type, "removed"))

    for nid in orig_set & mod_set:
        orig_data = orig_ids[nid].data.model_dump()
        mod_data = mod_ids[nid].data.model_dump()
        if orig_data != mod_data:
            # Find changed fields
            changed = [k for k in set(orig_data) | set(mod_data)
                       if orig_data.get(k) != mod_data.get(k)]
            result.nodes_modified.append(NodeDiff(
                nid, orig_ids[nid].data.type, "modified",
                details=f"changed fields: {', '.join(changed[:5])}"
            ))

    # Compare edges
    orig_edge_ids = {e.id for e in original.edges}
    mod_edge_ids = {e.id for e in modified.edges}
    result.edges_added = len(mod_edge_ids - orig_edge_ids)
    result.edges_removed = len(orig_edge_ids - mod_edge_ids)

    return result


def compare_files(file1: str | Path, file2: str | Path) -> CompareResult:
    """Compare two YAML files both structurally and textually.

    Returns:
        A CompareResult with both structural and text diffs.
    """
    from dify_dsl.parser import parse_dsl

    dsl1 = parse_dsl(file1)
    dsl2 = parse_dsl(file2)
    result = compare_dsl(dsl1, dsl2)

    # Text diff
    lines1 = Path(file1).read_text(encoding="utf-8").splitlines(keepends=True)
    lines2 = Path(file2).read_text(encoding="utf-8").splitlines(keepends=True)
    diff = difflib.unified_diff(lines1, lines2,
                                 fromfile=str(file1), tofile=str(file2), n=3)
    result.text_diff = "".join(diff)

    return result


def generate_html_diff(file1: str | Path, file2: str | Path, output: str | Path) -> None:
    """Generate an HTML side-by-side diff report."""
    lines1 = Path(file1).read_text(encoding="utf-8").splitlines()
    lines2 = Path(file2).read_text(encoding="utf-8").splitlines()

    differ = difflib.HtmlDiff()
    html = differ.make_file(lines1, lines2,
                             fromdesc=str(file1), todesc=str(file2),
                             context=True, numlines=3)
    Path(output).write_text(html, encoding="utf-8")
