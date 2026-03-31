"""Test parsing and round-trip generation with real Dify DSL files."""

import json
import tempfile
from pathlib import Path

import pytest

from dify_dsl import parse_dsl, parse_dsl_string, generate_dsl, generate_dsl_string
from dify_dsl.models import DifyDSL, Node
from dify_dsl.models.nodes import (
    LLMNodeData, CodeNodeData, StartNodeData, EndNodeData,
    QuestionClassifierNodeData, VariableAggregatorNodeData,
    McpServerNodeData, IfElseNodeData,
)
from dify_dsl.validator import validate
from dify_dsl.analyzer import analyze_topology, analyze_tools, analyze_variable_flow
from dify_dsl.splitter import split_workflow
from dify_dsl.rebuilder import rebuild_workflow
from dify_dsl.comparator import compare_dsl

# Reference DSL file
REFERENCE_DSL = Path("/Users/kevinten/projects/brag/ai_workflow/aierroranalysis/生产报错分析-报错分类及分析模块-v3.yml")


# ---------------------------------------------------------------------------
# Minimal DSL for unit tests (no external file dependency)
# ---------------------------------------------------------------------------

MINIMAL_DSL_YAML = """\
app:
  description: Test workflow
  icon: "🤖"
  icon_background: "#FFEAD5"
  mode: workflow
  name: test-workflow
  use_icon_as_answer_icon: false
dependencies: []
kind: app
version: "0.1.5"
workflow:
  conversation_variables: []
  environment_variables: []
  features:
    file_upload:
      enabled: false
    opening_statement: ""
  graph:
    edges:
    - data:
        sourceType: start
        targetType: llm
      id: edge-1
      source: node-start
      sourceHandle: source
      target: node-llm
      targetHandle: target
      type: custom
      zIndex: 0
    - data:
        sourceType: llm
        targetType: code
      id: edge-2
      source: node-llm
      sourceHandle: source
      target: node-code
      targetHandle: target
      type: custom
      zIndex: 0
    - data:
        sourceType: code
        targetType: end
      id: edge-3
      source: node-code
      sourceHandle: source
      target: node-end
      targetHandle: target
      type: custom
      zIndex: 0
    nodes:
    - data:
        type: start
        title: Start
        variables:
        - label: input
          variable: input
          type: string
          required: true
      id: node-start
      position: {x: 0, y: 0}
      type: custom
    - data:
        type: llm
        title: Classify Error
        model:
          provider: openai
          name: gpt-4o
          mode: chat
        prompt_template:
        - role: system
          text: You are an error classifier.
          edition_type: basic
        - role: user
          text: "Classify this error: {{#node-start.input#}}"
          edition_type: basic
      id: node-llm
      position: {x: 200, y: 0}
      type: custom
    - data:
        type: code
        title: Process Result
        code: |
          def main(result: str) -> dict:
              return {"output": result.strip()}
        code_language: python3
        variables:
        - variable: result
          value_selector:
          - node-llm
          - text
        outputs:
          output:
            type: string
      id: node-code
      position: {x: 400, y: 0}
      type: custom
    - data:
        type: end
        title: End
        outputs:
        - value_selector:
          - node-code
          - output
      id: node-end
      position: {x: 600, y: 0}
      type: custom
"""


class TestParseMinimal:
    """Test parsing with minimal inline DSL."""

    def test_parse_string(self):
        dsl = parse_dsl_string(MINIMAL_DSL_YAML)
        assert isinstance(dsl, DifyDSL)
        assert dsl.app.name == "test-workflow"
        assert dsl.version == "0.1.5"
        assert len(dsl.nodes) == 4
        assert len(dsl.edges) == 3

    def test_node_types(self):
        dsl = parse_dsl_string(MINIMAL_DSL_YAML)
        types = {n.data.type for n in dsl.nodes}
        assert types == {"start", "llm", "code", "end"}

    def test_typed_node_data(self):
        dsl = parse_dsl_string(MINIMAL_DSL_YAML)
        start = dsl.get_node("node-start")
        assert isinstance(start.data, StartNodeData)

        llm = dsl.get_node("node-llm")
        assert isinstance(llm.data, LLMNodeData)
        assert len(llm.data.prompt_template) == 2
        assert llm.data.prompt_template[0].role == "system"

        code = dsl.get_node("node-code")
        assert isinstance(code.data, CodeNodeData)
        assert "def main" in code.data.code
        assert code.data.code_language == "python3"

        end = dsl.get_node("node-end")
        assert isinstance(end.data, EndNodeData)

    def test_node_type_counts(self):
        dsl = parse_dsl_string(MINIMAL_DSL_YAML)
        counts = dsl.node_type_counts()
        assert counts == {"start": 1, "llm": 1, "code": 1, "end": 1}

    def test_get_nodes_by_type(self):
        dsl = parse_dsl_string(MINIMAL_DSL_YAML)
        llm_nodes = dsl.get_nodes_by_type("llm")
        assert len(llm_nodes) == 1
        assert llm_nodes[0].id == "node-llm"

    def test_round_trip(self):
        """Parse → generate → re-parse should produce equivalent structure."""
        dsl1 = parse_dsl_string(MINIMAL_DSL_YAML)
        yaml_str = generate_dsl_string(dsl1)
        dsl2 = parse_dsl_string(yaml_str)

        assert len(dsl1.nodes) == len(dsl2.nodes)
        assert len(dsl1.edges) == len(dsl2.edges)
        assert dsl1.app.name == dsl2.app.name
        assert dsl1.version == dsl2.version

        # Check node data preserved
        for n1 in dsl1.nodes:
            n2 = dsl2.get_node(n1.id)
            assert n2 is not None
            assert n1.data.type == n2.data.type
            assert n1.data.title == n2.data.title


class TestValidation:
    """Test DSL validation."""

    def test_valid_dsl(self):
        dsl = parse_dsl_string(MINIMAL_DSL_YAML)
        result = validate(dsl)
        assert result.is_valid

    def test_missing_start(self):
        yaml = MINIMAL_DSL_YAML.replace("type: start", "type: answer")
        dsl = parse_dsl_string(yaml)
        result = validate(dsl)
        assert not result.is_valid
        assert any("start" in e.lower() for e in result.errors)


class TestAnalysis:
    """Test workflow analysis."""

    def test_topology(self):
        dsl = parse_dsl_string(MINIMAL_DSL_YAML)
        topo = analyze_topology(dsl)
        assert len(topo.execution_levels) > 0
        assert len(topo.unreachable_nodes) == 0

    def test_variable_flow(self):
        dsl = parse_dsl_string(MINIMAL_DSL_YAML)
        vf = analyze_variable_flow(dsl)
        # LLM node references {{#node-start.input#}}
        assert "node-llm" in vf.reads


class TestSplitRebuild:
    """Test split → rebuild round trip."""

    def test_split_and_rebuild(self, tmp_path):
        dsl = parse_dsl_string(MINIMAL_DSL_YAML)

        # Split
        split_dir = tmp_path / "split"
        split_workflow(dsl, split_dir)

        # Verify split structure
        assert (split_dir / "metadata" / "workflow_info.json").exists()
        assert (split_dir / "metadata" / "edges.json").exists()
        assert (split_dir / "metadata" / "node_index.json").exists()
        assert (split_dir / "nodes" / "llm").is_dir()
        assert (split_dir / "nodes" / "code").is_dir()

        # Rebuild
        rebuilt = rebuild_workflow(split_dir)

        assert len(rebuilt.nodes) == len(dsl.nodes)
        assert len(rebuilt.edges) == len(dsl.edges)
        assert rebuilt.app.name == dsl.app.name

    def test_split_code_file(self, tmp_path):
        """Code nodes should produce standalone .py files."""
        dsl = parse_dsl_string(MINIMAL_DSL_YAML)
        split_dir = tmp_path / "split"
        split_workflow(dsl, split_dir)

        # Find the code node directory
        code_dirs = list((split_dir / "nodes" / "code").iterdir())
        assert len(code_dirs) == 1
        code_file = code_dirs[0] / "code.py"
        assert code_file.exists()
        assert "def main" in code_file.read_text()

    def test_split_prompts(self, tmp_path):
        """LLM nodes should produce separate prompt txt files."""
        dsl = parse_dsl_string(MINIMAL_DSL_YAML)
        split_dir = tmp_path / "split"
        split_workflow(dsl, split_dir)

        llm_dirs = list((split_dir / "nodes" / "llm").iterdir())
        assert len(llm_dirs) == 1
        llm_dir = llm_dirs[0]
        assert (llm_dir / "system_prompt_1.txt").exists()
        assert (llm_dir / "user_prompt_2.txt").exists()


class TestComparator:
    """Test DSL comparison."""

    def test_no_changes(self):
        dsl = parse_dsl_string(MINIMAL_DSL_YAML)
        result = compare_dsl(dsl, dsl)
        assert not result.has_changes

    def test_detect_added_node(self):
        from dify_dsl.models.nodes import Node, AnswerNodeData
        dsl1 = parse_dsl_string(MINIMAL_DSL_YAML)
        dsl2 = parse_dsl_string(MINIMAL_DSL_YAML)
        dsl2.workflow.graph.nodes.append(Node(
            id="extra-node",
            data=AnswerNodeData(type="answer", title="Extra"),
            position={"x": 800, "y": 0},
        ))
        result = compare_dsl(dsl1, dsl2)
        assert result.has_changes
        assert len(result.nodes_added) == 1


@pytest.mark.skipif(not REFERENCE_DSL.exists(), reason="Reference DSL not available")
class TestRealDSL:
    """Test with the real reference DSL file."""

    def test_parse_real(self):
        dsl = parse_dsl(REFERENCE_DSL)
        assert isinstance(dsl, DifyDSL)
        assert dsl.app.mode == "workflow"
        assert len(dsl.nodes) > 5

    def test_real_round_trip(self, tmp_path):
        dsl = parse_dsl(REFERENCE_DSL)
        out = tmp_path / "roundtrip.yml"
        generate_dsl(dsl, out)
        dsl2 = parse_dsl(out)

        assert len(dsl.nodes) == len(dsl2.nodes)
        assert len(dsl.edges) == len(dsl2.edges)

    def test_real_validate(self):
        dsl = parse_dsl(REFERENCE_DSL)
        result = validate(dsl)
        # Real DSL may have warnings but should parse without critical errors
        print(f"Valid: {result.is_valid}, Errors: {result.errors}, Warnings: {result.warnings}")

    def test_real_split_rebuild(self, tmp_path):
        dsl = parse_dsl(REFERENCE_DSL)
        split_dir = tmp_path / "real_split"
        split_workflow(dsl, split_dir)
        rebuilt = rebuild_workflow(split_dir)
        assert len(rebuilt.nodes) == len(dsl.nodes)

    def test_real_analyze(self):
        dsl = parse_dsl(REFERENCE_DSL)
        topo = analyze_topology(dsl)
        print(topo.summary)
        tools = analyze_tools(dsl)
        print(tools.summary)
