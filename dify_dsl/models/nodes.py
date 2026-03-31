"""Typed node models for all Dify node types.

Each node type has its own NodeData subclass with type-specific fields.
Unknown fields are preserved via ``extra="allow"`` for round-trip fidelity.

Usage:
    node_data = parse_node_data({"type": "llm", "title": "My LLM", ...})
    assert isinstance(node_data, LLMNodeData)
"""

from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class NodeData(BaseModel):
    """Base node data — all node types share these fields."""

    model_config = ConfigDict(extra="allow")

    type: str
    title: str = ""
    desc: str = ""


# ---------------------------------------------------------------------------
# Basic nodes
# ---------------------------------------------------------------------------

class StartNodeData(NodeData):
    """Start node — workflow entry point."""
    type: str = "start"
    variables: List[Any] = []


class EndNodeData(NodeData):
    """End node — workflow exit point."""
    type: str = "end"
    outputs: List[Any] = []


class AnswerNodeData(NodeData):
    """Answer node — direct response."""
    type: str = "answer"
    answer: str = ""


# ---------------------------------------------------------------------------
# Data processing nodes
# ---------------------------------------------------------------------------

class PromptItem(BaseModel):
    """A single prompt entry (system/user/assistant)."""
    model_config = ConfigDict(extra="allow")

    role: str = "user"
    text: str = ""
    edition_type: str = "basic"
    id: Optional[str] = None


class LLMNodeData(NodeData):
    """LLM node — large language model invocation."""
    type: str = "llm"
    model: Optional[Dict[str, Any]] = None
    prompt_template: List[PromptItem] = []
    memory: Optional[Dict[str, Any]] = None
    context: Optional[Dict[str, Any]] = None
    vision: Optional[Dict[str, Any]] = None


class CodeNodeData(NodeData):
    """Code node — executes Python/JS/TS code."""
    type: str = "code"
    code: str = ""
    code_language: str = "python3"
    variables: List[Any] = []
    outputs: Dict[str, Any] = {}


class TemplateTransformNodeData(NodeData):
    """Template transform node — Jinja2 template rendering."""
    type: str = "template_transform"
    template: str = ""
    variables: List[Any] = []


class VariableAggregatorNodeData(NodeData):
    """Variable aggregator — merges multiple variable sources."""
    type: str = "variable_aggregator"
    variables: List[Any] = []
    output_type: str = "string"
    advanced_settings: Optional[Dict[str, Any]] = None


class VariableAssignerNodeData(NodeData):
    """Variable assigner — sets variable values."""
    type: str = "variable_assigner"
    items: List[Any] = []


class KnowledgeRetrievalNodeData(NodeData):
    """Knowledge retrieval — RAG knowledge base query."""
    type: str = "knowledge_retrieval"
    dataset_ids: List[str] = []
    retrieval_mode: str = "single"
    query_variable_selector: List[Any] = []


# ---------------------------------------------------------------------------
# Logic control nodes
# ---------------------------------------------------------------------------

class IfElseNodeData(NodeData):
    """Conditional branching node."""
    type: str = "if_else"
    conditions: List[Any] = []
    logical_operator: str = "and"


class IterationNodeData(NodeData):
    """Iteration node — loops over a list."""
    type: str = "iteration"
    iterator_selector: List[Any] = []
    output_selector: List[Any] = []
    start_node_id: str = ""
    output_type: str = "array"


class IterationStartNodeData(NodeData):
    """Iteration start marker (inside iteration blocks)."""
    type: str = "iteration_start"


class LoopNodeData(NodeData):
    """Loop node."""
    type: str = "loop"


# ---------------------------------------------------------------------------
# External integration nodes
# ---------------------------------------------------------------------------

class HttpRequestNodeData(NodeData):
    """HTTP request node."""
    type: str = "http_request"
    method: str = "GET"
    url: str = ""
    headers: Any = ""  # Can be string or list depending on Dify version
    params: Any = ""
    body: Optional[Dict[str, Any]] = None
    authorization: Optional[Dict[str, Any]] = None
    timeout: Optional[Dict[str, Any]] = None


class ToolNodeData(NodeData):
    """External tool invocation node."""
    type: str = "tool"
    provider_id: str = ""
    provider_type: str = ""
    provider_name: str = ""
    tool_name: str = ""
    tool_label: str = ""
    tool_parameters: Dict[str, Any] = {}
    tool_configurations: Dict[str, Any] = {}


class AgentNodeData(NodeData):
    """Agent node — autonomous agent with tools."""
    type: str = "agent"
    agent_strategy_provider_name: str = ""
    agent_strategy_name: str = ""
    agent_parameters: Dict[str, Any] = {}
    prompt_template: List[PromptItem] = []


class QuestionClassifierNodeData(NodeData):
    """Question classifier — routes based on question type."""
    type: str = "question-classifier"
    model: Optional[Dict[str, Any]] = None
    query_variable_selector: List[Any] = []
    classes: List[Any] = []
    instruction: str = ""


class McpServerNodeData(NodeData):
    """MCP (Model Context Protocol) server node."""
    type: str = "mcp-server"
    mcp_server_ids: List[str] = []
    mcp_tools: List[Any] = []
    output_type: str = "text"


# ---------------------------------------------------------------------------
# Utility nodes
# ---------------------------------------------------------------------------

class ParameterExtractorNodeData(NodeData):
    """Parameter extractor — extracts structured data from text."""
    type: str = "parameter_extractor"
    model: Optional[Dict[str, Any]] = None
    query: List[Any] = []
    parameters: List[Any] = []
    instruction: str = ""


class ListFilterNodeData(NodeData):
    """List filter — filters items in a list."""
    type: str = "list_filter"


class DocExtractorNodeData(NodeData):
    """Document extractor — extracts content from documents."""
    type: str = "doc_extractor"


# ---------------------------------------------------------------------------
# Trigger nodes
# ---------------------------------------------------------------------------

class TriggerWebhookNodeData(NodeData):
    """Webhook trigger node."""
    type: str = "trigger_webhook"


class TriggerScheduleNodeData(NodeData):
    """Schedule trigger node."""
    type: str = "trigger_schedule"


class TriggerPluginNodeData(NodeData):
    """Plugin trigger node."""
    type: str = "trigger_plugin"


# ---------------------------------------------------------------------------
# Node container
# ---------------------------------------------------------------------------

class Node(BaseModel):
    """A workflow graph node wrapping typed NodeData."""

    model_config = ConfigDict(extra="allow")

    id: str
    data: NodeData
    position: Dict[str, Any] = {}
    height: Optional[float] = None
    width: Optional[float] = None
    selected: bool = False
    sourcePosition: str = "right"
    targetPosition: str = "left"
    type: str = "custom"
    zIndex: int = 0
    parentId: Optional[str] = None
    extent: Optional[str] = None


# ---------------------------------------------------------------------------
# Node data registry & factory
# ---------------------------------------------------------------------------

_NODE_DATA_REGISTRY: Dict[str, type] = {
    "start": StartNodeData,
    "end": EndNodeData,
    "answer": AnswerNodeData,
    "llm": LLMNodeData,
    "code": CodeNodeData,
    "template_transform": TemplateTransformNodeData,
    "variable_aggregator": VariableAggregatorNodeData,
    "variable-aggregator": VariableAggregatorNodeData,
    "variable_assigner": VariableAssignerNodeData,
    "variable-assigner": VariableAssignerNodeData,
    "knowledge_retrieval": KnowledgeRetrievalNodeData,
    "knowledge-retrieval": KnowledgeRetrievalNodeData,
    "if_else": IfElseNodeData,
    "if-else": IfElseNodeData,
    "iteration": IterationNodeData,
    "iteration_start": IterationStartNodeData,
    "iteration-start": IterationStartNodeData,
    "loop": LoopNodeData,
    "http_request": HttpRequestNodeData,
    "http-request": HttpRequestNodeData,
    "tool": ToolNodeData,
    "agent": AgentNodeData,
    "question_classifier": QuestionClassifierNodeData,
    "question-classifier": QuestionClassifierNodeData,
    "mcp_server": McpServerNodeData,
    "mcp-server": McpServerNodeData,
    "parameter_extractor": ParameterExtractorNodeData,
    "parameter-extractor": ParameterExtractorNodeData,
    "list_filter": ListFilterNodeData,
    "list-filter": ListFilterNodeData,
    "doc_extractor": DocExtractorNodeData,
    "doc-extractor": DocExtractorNodeData,
    "trigger_webhook": TriggerWebhookNodeData,
    "trigger_schedule": TriggerScheduleNodeData,
    "trigger_plugin": TriggerPluginNodeData,
}


def parse_node_data(raw: Dict[str, Any]) -> NodeData:
    """Parse raw dict into the appropriate typed NodeData subclass.

    Unknown node types fall back to the generic ``NodeData`` base,
    preserving all fields via ``extra="allow"``.
    """
    node_type = raw.get("type", "")
    cls = _NODE_DATA_REGISTRY.get(node_type, NodeData)
    return cls.model_validate(raw)


def parse_node(raw: Dict[str, Any]) -> Node:
    """Parse a raw node dict into a typed Node with typed NodeData."""
    data_raw = raw.get("data", {})
    typed_data = parse_node_data(data_raw)
    node_fields = {k: v for k, v in raw.items() if k != "data"}
    node_fields["data"] = typed_data
    return Node.model_validate(node_fields)
