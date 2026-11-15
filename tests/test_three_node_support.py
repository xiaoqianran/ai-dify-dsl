"""复现 Dify 实际使用的三类节点，并验证专用类型和可编辑拆分。"""
from copy import deepcopy
from pathlib import Path

import pytest

from dify_dsl import generate_dsl_string, parse_dsl_string
from dify_dsl.models.nodes import (
    LoopStartNodeData,
    TemplateTransformNodeData,
    VariableAssignerNodeData,
    parse_node_data,
)
from dify_dsl.parser import _load_yaml, _load_yaml_string
from dify_dsl.python_sync import parse_python_source, to_python_source
from dify_dsl.rebuilder import rebuild_workflow
from dify_dsl.splitter import split_workflow

FIXTURE_DIR = Path('/tmp/dify-node-fixtures')


def _require_official_fixture(filename: str) -> Path:
    path = FIXTURE_DIR / filename
    if not path.is_file():
        pytest.skip('未安装 Dify 官方工作流样例')
    return path
CASES = [
    ('template-transform', 'array_iteration_formatting_workflow.yml', TemplateTransformNodeData),
    ('loop-start', 'increment_loop_with_break_condition_workflow.yml', LoopStartNodeData),
    ('assigner', 'increment_loop_with_break_condition_workflow.yml', VariableAssignerNodeData),
]


@pytest.mark.parametrize('node_type,fixture,expected_type', CASES)
def test_official_sample_parses_into_dedicated_type(node_type, fixture, expected_type):
    if not (FIXTURE_DIR / fixture).exists():
        pytest.skip('Dify 官方样例未安装')
    raw = _load_yaml(FIXTURE_DIR / fixture)
    parsed = parse_dsl_string(generate_dsl_string(__import__('dify_dsl').DifyDSL.model_validate(deepcopy(raw))))
    matching = [n for n in parsed.nodes if n.data.type == node_type]
    assert matching
    assert all(isinstance(n.data, expected_type) for n in matching)
    assert _load_yaml_string(generate_dsl_string(parsed)) == raw
    assert _load_yaml_string(generate_dsl_string(parse_python_source(to_python_source(parsed)))) == raw


@pytest.mark.parametrize('node_type,fixture,_', CASES)
def test_official_sample_split_rebuild_is_exact(node_type, fixture, _, tmp_path):
    if not (FIXTURE_DIR / fixture).exists():
        pytest.skip('Dify 官方样例未安装')
    raw = _load_yaml(FIXTURE_DIR / fixture)
    dsl = __import__('dify_dsl').DifyDSL.model_validate(deepcopy(raw))
    folder = split_workflow(dsl, tmp_path / 'split')
    rebuilt = rebuild_workflow(folder)
    assert _load_yaml_string(generate_dsl_string(rebuilt)) == raw


def test_template_transform_edit_in_split_file_survives_rebuild(tmp_path):
    raw = _load_yaml(_require_official_fixture('array_iteration_formatting_workflow.yml'))
    original = __import__('dify_dsl').DifyDSL.model_validate(deepcopy(raw))
    node = next(n for n in original.nodes if n.data.type == 'template-transform')
    folder = split_workflow(original, tmp_path / 'split')
    template_file = next((folder / 'nodes' / 'template-transform').glob('*/template.txt'))
    old = template_file.read_text(encoding='utf-8')
    assert old == node.data.template
    new = old + '\n{{ arg1 | upper }}'
    template_file.write_text(new, encoding='utf-8')
    rebuilt = rebuild_workflow(folder)
    updated = next(n for n in rebuilt.nodes if n.id == node.id)
    assert updated.data.template == new
    assert updated.data.type == 'template-transform'
    assert updated.parentId == node.parentId


def test_loop_start_parent_and_assigner_operation_survive_edit(tmp_path):
    raw = _load_yaml(_require_official_fixture('increment_loop_with_break_condition_workflow.yml'))
    original = __import__('dify_dsl').DifyDSL.model_validate(deepcopy(raw))
    start = next(n for n in original.nodes if n.data.type == 'loop-start')
    assigner = next(n for n in original.nodes if n.data.type == 'assigner')
    folder = split_workflow(original, tmp_path / 'split')
    assigner_config = next((folder / 'nodes' / 'assigner').glob('*/config.yaml'))
    config = _load_yaml(assigner_config)
    original_items = config['items']
    assert original_items[0]['operation'] == '+='
    config['items'][0]['value'] = 3
    from dify_dsl.splitter import _dump_yaml
    _dump_yaml(config, assigner_config)
    rebuilt = rebuild_workflow(folder)
    final_start = next(n for n in rebuilt.nodes if n.id == start.id)
    final_assigner = next(n for n in rebuilt.nodes if n.id == assigner.id)
    assert final_start.parentId == start.parentId
    assert final_start.data.isInLoop is True
    assert final_assigner.data.items[0]['operation'] == '+='
    assert final_assigner.data.items[0]['variable_selector'] == original_items[0]['variable_selector']
    assert final_assigner.data.items[0]['value'] == 3
    assert final_assigner.data.type == 'assigner'


def test_all_three_types_preserve_future_unknown_fields():
    for name, _, expected_type in CASES:
        raw = {'type':name,'title':'未来节点','version':'99',
               'unknown_config':{'nested':[1,None,{'boolean':True,'message':'中文'}]}}
        item = parse_node_data(raw)
        assert isinstance(item, expected_type)
        assert item.model_dump(exclude_unset=True) == raw


def test_legacy_template_split_directory_without_template_txt_still_rebuilds(tmp_path):
    """兼容修复前的通用 NodeData 拆分产物，避免向后不兼容。"""
    from dify_dsl.models.nodes import _NODE_DATA_REGISTRY
    raw = _load_yaml(_require_official_fixture('array_iteration_formatting_workflow.yml'))
    template_class = _NODE_DATA_REGISTRY.pop('template-transform')
    try:
        legacy = __import__('dify_dsl').DifyDSL.model_validate(deepcopy(raw))
        folder = split_workflow(legacy, tmp_path / 'legacy')
    finally:
        _NODE_DATA_REGISTRY['template-transform'] = template_class
    assert not list(folder.rglob('template.txt'))
    # 修复后的重建器应仍能读取旧 config.yaml 中的模板原文字段。
    assert _load_yaml_string(generate_dsl_string(rebuild_workflow(folder))) == raw


def test_model_validation_does_not_mutate_caller_source_dict():
    """回归：Dify 实际导出后的原始 dict 可反复被转换、比较和复用。"""
    from dify_dsl import DifyDSL
    original = _load_yaml(_require_official_fixture('increment_loop_with_break_condition_workflow.yml'))
    before = deepcopy(original)
    first = DifyDSL.model_validate(original)
    assert original == before
    assert isinstance(original['workflow']['graph']['nodes'][0], dict)
    second = DifyDSL.model_validate(original)
    assert original == before
    assert _load_yaml_string(generate_dsl_string(first)) == before
    assert _load_yaml_string(generate_dsl_string(second)) == before


@pytest.mark.parametrize('kind', ['template', 'loop', 'assigner'])
def test_actual_dify_server_export_is_lossless_and_immutable(kind, tmp_path):
    """服务器已发布工作流的真实导出可重复读写，不反向修改原始 dict。"""
    from dify_dsl import DifyDSL
    from dify_dsl.python_sync import to_python_source, parse_python_source
    path = Path(__file__).parent.parent / 'integration_tests' / 'dify_three_nodes' / (kind + '.server-export.yml')
    if not path.exists():
        pytest.skip('尚未保存 Dify 实际导出样例')
    original = _load_yaml(path)
    snapshot = deepcopy(original)
    model = DifyDSL.model_validate(original)
    assert original == snapshot
    assert _load_yaml_string(generate_dsl_string(model)) == snapshot
    assert _load_yaml_string(generate_dsl_string(parse_python_source(to_python_source(model)))) == snapshot
    assert original == snapshot
