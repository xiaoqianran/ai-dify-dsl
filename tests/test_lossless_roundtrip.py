"""防止真实 Dify 工作流经过转换后静默丢失节点字段。"""
from pathlib import Path

from dify_dsl import generate_dsl, generate_dsl_string, parse_dsl, parse_dsl_string
from dify_dsl.parser import _load_yaml, _load_yaml_string
from dify_dsl.rebuilder import rebuild_workflow
from dify_dsl.splitter import split_workflow
from dify_dsl.validator import validate

FIXTURE = Path(__file__).parent / 'fixtures' / 'excel-analysis-workflow.yml'


def test_excel_generator_is_lossless(tmp_path):
    original = _load_yaml(FIXTURE)
    dsl = parse_dsl(FIXTURE)
    serialized = _load_yaml_string(generate_dsl_string(dsl))
    assert serialized == original
    output = tmp_path / 'regenerated.yml'
    generate_dsl(dsl, output)
    assert _load_yaml(output) == original
    assert validate(parse_dsl(output)).is_valid


def test_excel_split_rebuild_is_lossless(tmp_path):
    original = _load_yaml(FIXTURE)
    folder = split_workflow(parse_dsl(FIXTURE), tmp_path / 'split')
    rebuilt = rebuild_workflow(folder)
    output = tmp_path / 'rebuilt.yml'
    generate_dsl(rebuilt, output)
    assert _load_yaml(output) == original
    assert validate(parse_dsl(output)).is_valid


def test_split_code_remains_editable(tmp_path):
    folder = split_workflow(parse_dsl(FIXTURE), tmp_path / 'split')
    code_file = next((folder / 'nodes' / 'code').glob('*/code.py'))
    updated_code = code_file.read_text() + '\n# 编辑后保留\n'
    code_file.write_text(updated_code)
    rebuilt = rebuild_workflow(folder)
    code = next(node.data.code for node in rebuilt.nodes if node.data.type == 'code')
    assert code == updated_code


def test_subclass_fields_and_unknown_fields_are_preserved():
    original = _load_yaml(FIXTURE)
    code_data = original['workflow']['graph']['nodes'][2]['data']
    code_data['new_future_option'] = {'enabled': True, 'items': [1, 2]}
    original['workflow']['graph']['nodes'][2]['frontend_extension'] = {'notes': '保留'}
    original['workflow']['graph']['new_graph_option'] = 'future'
    from ruamel.yaml import YAML
    from io import StringIO
    yaml = YAML()
    buf = StringIO()
    yaml.dump(original, buf)
    regenerated = generate_dsl_string(parse_dsl_string(buf.getvalue()))
    assert _load_yaml_string(regenerated) == original


def test_llm_and_code_workflow_roundtrip(tmp_path):
    # 包含 LLM Prompt 与 Code 的多节点示例，避免只覆盖 Excel 案例。
    from tests.test_parse_roundtrip import MINIMAL_DSL_YAML
    raw = _load_yaml_string(MINIMAL_DSL_YAML)
    source = parse_dsl_string(MINIMAL_DSL_YAML)
    assert _load_yaml_string(generate_dsl_string(source)) == raw
    split_dir = split_workflow(source, tmp_path / 'llm-split')
    assert _load_yaml_string(generate_dsl_string(rebuild_workflow(split_dir))) == raw
