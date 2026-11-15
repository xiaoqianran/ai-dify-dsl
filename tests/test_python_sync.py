"""全节点双向数据保真、编辑传播和冲突保护。"""

import json
from copy import deepcopy

import pytest

from dify_dsl import generate_dsl_string, parse_dsl_string
from dify_dsl.models.nodes import _NODE_DATA_REGISTRY
from dify_dsl.parser import _load_yaml_string
from dify_dsl.python_sync import (
    SyncConflictError,
    dsl_to_python,
    parse_python_source,
    python_to_dsl,
    python_to_yaml,
    sync_pair,
    to_python_source,
)
from dify_dsl.rebuilder import rebuild_workflow
from dify_dsl.splitter import split_workflow


@pytest.fixture
def all_nodes_document():
    # 覆盖注册表每个 node type 与额外的未来未知节点：验证数据保真，不代表各节点可直接执行。
    types = list(_NODE_DATA_REGISTRY)
    types.extend(['document-extractor', 'future-node-that-does-not-exist'])
    nodes = []
    for i, node_type in enumerate(types):
        data = {
            'type': node_type,
            'title': f'节点{i}',
            'desc': '含中文、emoji 和嵌套字段 ✅',
            'extra_future_option': {'nested': [1, None, True, {'v': '中文'}]},
        }
        if node_type == 'code':
            data.update(code='def main(x: str) -> dict:\n    return {"x": x}\n', code_language='python3',
                        variables=[{'variable': 'x', 'value_selector': ['start', 'text']}],
                        outputs={'x': {'type': 'string', 'children': None}})
        if node_type == 'llm':
            data['prompt_template'] = [{'role': 'system', 'text': '中文提示词', 'edition_type': 'basic'},
                                       {'role': 'user', 'text': '{{#start.text#}}'}]
        if node_type in ('http_request', 'http-request'):
            data['headers'] = [{'key': 'X-A', 'value': 'B'}]
        if node_type == 'start':
            data['variables'] = [{'variable': 'text', 'label': 'text', 'type': 'text-input'}]
        nodes.append({'id': f'id_{i}', 'type': 'custom', 'position': {'x': i * 100, 'y': 0},
                      'data': data, 'node_extra': [node_type, None]})
    return {
        'app': {'name': '全节点往返测试', 'mode': 'workflow', 'description': 'synthetic'},
        'kind': 'app', 'version': '0.7.0', 'unknown_top': {'data': 1},
        'workflow': {
            'features': {'file_upload': {'enabled': False}},
            'conversation_variables': [], 'environment_variables': [],
            'unrecognized_workflow_field': '保留',
            'graph': {'nodes': nodes, 'edges': [], 'viewport': {'x': 1, 'y': 2, 'zoom': 0.8}},
        },
    }


def test_each_registry_type_can_roundtrip_through_python(all_nodes_document):
    original = all_nodes_document
    dsl = parse_dsl_string(generate_dsl_string(__import__('dify_dsl').DifyDSL.model_validate(deepcopy(original))))
    source = to_python_source(dsl)
    assert _load_yaml_string(generate_dsl_string(parse_python_source(source))) == original
    assert len(dsl.nodes) == len(_NODE_DATA_REGISTRY) + 2


def test_each_registry_type_can_split_rebuild(all_nodes_document, tmp_path):
    dsl = __import__('dify_dsl').DifyDSL.model_validate(deepcopy(all_nodes_document))
    result = rebuild_workflow(split_workflow(dsl, tmp_path / 'all_nodes'))
    assert _load_yaml_string(generate_dsl_string(result)) == all_nodes_document


def test_sync_propagates_changes_in_both_directions(tmp_path):
    yml, py = tmp_path / 'workflow.yml', tmp_path / 'workflow.py'
    original = _load_yaml_string((__import__('pathlib').Path(__file__).parent / 'fixtures' / 'excel-analysis-workflow.yml').read_text())
    yml.write_text(generate_dsl_string(__import__('dify_dsl').DifyDSL.model_validate(deepcopy(original))))
    assert sync_pair(yml, py) == 'yaml-to-python'
    assert sync_pair(yml, py) == 'unchanged'

    # Python 改代码，再同步回 YAML。
    py_source = py.read_text().replace('检测到 %d 个表格', '统计到 %d 个表格')
    py.write_text(py_source)
    assert sync_pair(yml, py) == 'python-to-yaml'
    assert '统计到 %d 个表格' in yml.read_text()

    # YAML 修改标题，再同步回 Python。
    yaml_text = yml.read_text().replace('Excel 表格质量分析', 'Excel 表格质量分析 V2')
    yml.write_text(yaml_text)
    assert sync_pair(yml, py) == 'yaml-to-python'
    assert python_to_dsl(py).app.name == 'Excel 表格质量分析 V2'
    assert sync_pair(yml, py) == 'unchanged'


def test_conflicting_edits_do_not_overwrite_files(tmp_path):
    yml, py = tmp_path / 'workflow.yml', tmp_path / 'workflow.py'
    source = __import__('pathlib').Path(__file__).parent / 'fixtures' / 'excel-analysis-workflow.yml'
    yml.write_bytes(source.read_bytes())
    sync_pair(yml, py)
    yml.write_text(yml.read_text().replace('Excel 表格质量分析', 'YAML 改动'))
    py.write_text(py.read_text().replace('Excel 表格质量分析', 'PYTHON 改动'))
    before_yaml, before_py = yml.read_bytes(), py.read_bytes()
    with pytest.raises(SyncConflictError, match='冲突'):
        sync_pair(yml, py)
    assert yml.read_bytes() == before_yaml
    assert py.read_bytes() == before_py


def test_initial_divergence_and_existing_destinations_are_protected(tmp_path):
    source = __import__('pathlib').Path(__file__).parent / 'fixtures' / 'excel-analysis-workflow.yml'
    yml, py = tmp_path / 'workflow.yml', tmp_path / 'workflow.py'
    yml.write_bytes(source.read_bytes())
    dsl_to_python(yml, py)
    py.write_text(py.read_text().replace('Excel 表格质量分析', 'Different'))
    with pytest.raises(SyncConflictError, match='首次同步'):
        sync_pair(yml, py)
    with pytest.raises(SyncConflictError, match='已存在'):
        dsl_to_python(yml, py)
    with pytest.raises(SyncConflictError, match='已存在'):
        python_to_yaml(py, yml)


def test_python_parser_does_not_execute_code(tmp_path):
    marker = tmp_path / 'must_not_exist'
    malicious = f"WORKFLOW_DSL = __import__('os').system('touch {marker}')"
    with pytest.raises(ValueError, match='字面量'):
        parse_python_source(malicious)
    assert not marker.exists()
    with pytest.raises(ValueError, match='只能包含'):
        parse_python_source('WORKFLOW_DSL = {}\nprint(123)')


def test_python_source_roundtrip_is_stable(all_nodes_document):
    import dify_dsl
    obj = dify_dsl.DifyDSL.model_validate(deepcopy(all_nodes_document))
    original_python = to_python_source(obj)
    assert to_python_source(parse_python_source(original_python)) == original_python


def test_javascript_code_node_roundtrip(tmp_path):
    import dify_dsl
    source = _load_yaml_string((__import__('pathlib').Path(__file__).parent / 'fixtures' / 'excel-analysis-workflow.yml').read_text())
    node = source['workflow']['graph']['nodes'][2]['data']
    node['code_language'] = 'javascript'
    node['code'] = 'function main({ input }) { return { result: input }; }\n'
    typed = dify_dsl.DifyDSL.model_validate(deepcopy(source))
    py = to_python_source(typed)
    assert _load_yaml_string(generate_dsl_string(parse_python_source(py))) == source
    rebuilt = rebuild_workflow(split_workflow(typed, tmp_path / 'js-split'))
    assert _load_yaml_string(generate_dsl_string(rebuilt)) == source
    assert list((tmp_path / 'js-split' / 'nodes' / 'code').glob('*/code.js'))


def test_watch_synchronizes_changed_python(tmp_path, monkeypatch, capsys):
    import dify_dsl.python_sync as module
    source = __import__('pathlib').Path(__file__).parent / 'fixtures' / 'excel-analysis-workflow.yml'
    yaml_file, py_file = tmp_path / 'workflow.yml', tmp_path / 'workflow.py'
    yaml_file.write_bytes(source.read_bytes())
    module.sync_pair(yaml_file, py_file)
    py_file.write_text(py_file.read_text().replace('Excel 表格质量分析', '自动同步已修改'))
    calls = []

    def stop_after_one_poll(interval):
        calls.append(interval)
        raise KeyboardInterrupt()

    monkeypatch.setattr('time.sleep', stop_after_one_poll)
    module.watch_pair(yaml_file, py_file, interval=0.1)
    assert calls == [0.1]
    assert module.parse_dsl(yaml_file).app.name == '自动同步已修改'
    assert 'python-to-yaml' in capsys.readouterr().out
