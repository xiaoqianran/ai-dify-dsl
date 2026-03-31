"""
Dify DSL Parser & Generator
============================

A typed parser/generator for Dify workflow DSL files.
Enables local editing and optimization of Dify workflows.

Usage:
    from dify_dsl import parse_dsl, generate_dsl

    # Parse a Dify DSL YAML file into typed models
    dsl = parse_dsl("workflow.yml")

    # Access typed workflow data
    for node in dsl.workflow.graph.nodes:
        print(f"{node.id}: {node.data.type} - {node.data.title}")

    # Generate back to YAML
    generate_dsl(dsl, "output.yml")
"""

from dify_dsl.models import DifyDSL, DifyApp, Workflow, Graph, Edge, Node, NodeData
from dify_dsl.parser import parse_dsl, parse_dsl_string
from dify_dsl.generator import generate_dsl, generate_dsl_string

__version__ = "3.0.0"

__all__ = [
    "DifyDSL",
    "DifyApp",
    "Workflow",
    "Graph",
    "Edge",
    "Node",
    "NodeData",
    "parse_dsl",
    "parse_dsl_string",
    "generate_dsl",
    "generate_dsl_string",
]
