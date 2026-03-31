"""Workflow, graph, and edge models."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict


class EdgeData(BaseModel):
    """Metadata attached to a graph edge."""

    model_config = ConfigDict(extra="allow")

    isInIteration: bool = False
    isInLoop: bool = False
    sourceType: str = ""
    targetType: str = ""


class Edge(BaseModel):
    """A directed edge between two nodes in the workflow graph."""

    model_config = ConfigDict(extra="allow")

    id: str
    source: str
    sourceHandle: str = "source"
    target: str
    targetHandle: str = "target"
    type: str = "custom"
    zIndex: int = 0
    data: EdgeData = EdgeData()
    selected: bool = False


class Graph(BaseModel):
    """The workflow graph containing nodes and edges.

    Note: nodes are stored as raw dicts here and converted to typed
    Node objects by the DifyDSL model. This avoids circular imports
    and keeps the graph model simple.
    """

    model_config = ConfigDict(extra="allow")

    nodes: List[Any] = []  # List[Node] — resolved at DifyDSL level
    edges: List[Edge] = []


class Features(BaseModel):
    """Workflow feature flags and configuration."""

    model_config = ConfigDict(extra="allow")

    file_upload: Optional[Dict[str, Any]] = None
    opening_statement: str = ""
    retriever_resource: Optional[Dict[str, Any]] = None
    sensitive_word_avoidance: Optional[Dict[str, Any]] = None
    speech_to_text: Optional[Dict[str, Any]] = None
    suggested_questions: List[Any] = []
    suggested_questions_after_answer: Optional[Dict[str, Any]] = None
    text_to_speech: Optional[Dict[str, Any]] = None


class Workflow(BaseModel):
    """The workflow definition including graph, variables, and features."""

    model_config = ConfigDict(extra="allow")

    conversation_variables: List[Any] = []
    environment_variables: List[Any] = []
    features: Features = Features()
    graph: Graph = Graph()
