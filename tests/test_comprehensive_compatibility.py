"""Dify 官方安装包工作流、全类型配置与跨表示编辑的兼容性回归测试。

Dify 官方样例路径由 DIFY_WORKFLOW_FIXTURES 指定；不存在时仅跳过这批集成测试。
官方样例不加入仓库，保留上游出处与版本。
"""
import json
import os
from copy import deepcopy
from pathlib import Path

import pytest

from dify_dsl import DifyDSL, generate_dsl_string, parse_dsl_string
from dify_dsl.models.nodes import _NODE_DATA_REGISTRY
from dify_dsl.parser import _load_yaml_string, _load_yaml
from dify_dsl.python_sync import to_python_source, parse_python_source, sync_pair
from dify_dsl.splitter import split_workflow
from dify_dsl.rebuilder import rebuild_workflow

OFFICIAL_DIR = Path(os.getenv('DIFY_WORKFLOW_FIXTURES', '/tmp/dify-node-fixtures'))
OFFICIAL_CASES = sorted(OFFICIAL_DIR.glob('*.yml'))
EXTERNAL_CASES = [
    Path('/workspace/wk/dify-rag/paper-research/research-report-workflow.yml'),
    Path('/workspace/wk/dify-rag/paper-research/corpus/resnet/resnet-research-workflow.yml'),
    Path('/workspace/wk/dify-rag/excel-analysis-workflow.yml'),
]


def assert_lossless(raw):
    source = parse_dsl_string(generate_dsl_string(DifyDSL.model_validate(deepcopy(raw))))
    assert _load_yaml_string(generate_dsl_string(source)) == raw
    assert _load_yaml_string(generate_dsl_string(parse_python_source(to_python_source(source)))) == raw
    return source


@pytest.mark.parametrize('official', OFFICIAL_CASES, ids=lambda p: p.stem)
def test_installed_dify_official_fixture_is_lossless(official, tmp_path):
    raw = _load_yaml(official)
    original = assert_lossless(raw)
    parts = split_workflow(original, tmp_path / official.stem)
    assert _load_yaml_string(generate_dsl_string(rebuild_workflow(parts))) == raw
    # Both directions of edit propagation for an official complex workflow.
    yaml_path = tmp_path / 'workflow.yml'
    py_path = tmp_path / 'workflow.py'
    yaml_path.write_text(generate_dsl_string(original), encoding='utf-8')
    assert sync_pair(yaml_path, py_path) == 'yaml-to-python'
    assert sync_pair(yaml_path, py_path) == 'unchanged'
    py_path.write_text(py_path.read_text(encoding='utf-8').replace('WORKFLOW_DSL', 'WORKFLOW_DSL'))
    assert sync_pair(yaml_path, py_path) == 'unchanged'


@pytest.mark.parametrize('path', EXTERNAL_CASES, ids=lambda p: p.stem)
def test_actual_deployed_workflow_is_lossless(path, tmp_path):
    if not path.exists():
        pytest.skip('User workflow not mounted')
    raw = _load_yaml(path)
    original = assert_lossless(raw)
    parts = split_workflow(original, tmp_path / path.stem)
    assert _load_yaml_string(generate_dsl_string(rebuild_workflow(parts))) == raw


def test_every_known_alias_and_forward_compatible_unknown_roundtrip(tmp_path):
    """Full-graph with all registered aliases, nested fields, edges, future unknown type."""
    types = list(_NODE_DATA_REGISTRY) + ['document-extractor', 'iteration-end', 'future-plugin-node']
    nodes = []
    for index, typ in enumerate(types):
        data = {
            'type':typ,
            'title':f'兼容性_{typ}',
            'desc':'字段保真测试',
            'new_api_field': {'nested': {'booleans':[True,False,None], 'zh':'中文🚀', 'integer': 131072}},
            'version_specific': {'meta': [{'x': 'test', 'arr': [1,2,3]}, None]},
        }
        if typ=='llm':
            data.update(model={'name':'reasoner','provider':'provider','mode':'chat','completion_params':{'max_tokens':131072,'extra_body':{'thinking':{'budget':20000}}}},prompt_template=[{'role':'system','text':'复杂多节点测试'},{'role':'user','text':'{{#start.text#}}'}])
        if typ=='agent':
            data.update(agent_strategy_provider_name='agent',agent_parameters={'tools':[{'name':'search','parameters':{'q':'text'}}]})
        if typ=='code':
            data.update(code_language='python3',code='def main(x: str) -> dict:\n    return {"result": x}\n',outputs={'result':{'type':'string'}},variables=[{'variable':'x','value_selector':['start','text']}])
        if typ in ('loop','iteration'):
            data.update(start_node_id=f'n{index}-start',nested_node_ids=[f'n{index}-start'],loop_count=4,break_conditions=[{'operator':'is','value':True}],error_handle_mode='terminated')
        if typ in ('tool','mcp_server','mcp-server'):
            data['plugin_config']={'authorization':{'type':'secret-variable','ref':'env.TOKEN'},'inputs':[{'x':1}]}
        if typ=='http-request' or typ=='http_request':
            data.update(method='POST',url='https://example.org',body={'type':'json','data':'{"x": 1}'},authorization={'type':'api-key','config':{'api_key':'{{#env.SECRET#}}'}})
        nodes.append({'id':f'n{index}','type':'custom','position':{'x':index*190,'y':0},'positionAbsolute':{'x':index*190,'y':0},'data':data,'width':244,'height':100,'parentId':None,'frontend_extension':{'nested':True}})
    edges=[]
    for i in range(len(nodes)-1):
        edges.append({'id':f'edge{i}','source':f'n{i}','target':f'n{i+1}','sourceHandle':'source','targetHandle':'target','type':'custom','data':{'sourceType':types[i],'targetType':types[i+1],'advanced':{'route':i}},'selected':False})
    raw={'app':{'name':'全部节点混合图','mode':'workflow','description':'stress'},'kind':'app','version':'0.7.0','future_root':{'list':[1,2]},'workflow':{'conversation_variables':[{'name':'state','value_type':'number','value':0}],'environment_variables':[{'name':'SECRET','value_type':'secret','value':'placeholder'}],'features':{'file_upload':{'enabled':False},'future_flags':['a','b']},'graph':{'nodes':nodes,'edges':edges,'viewport':{'x':0,'y':0,'zoom':0.5},'graph_extension':{'x':42}}}}
    source=assert_lossless(raw)
    assert len(source.nodes)==len(types)
    out=split_workflow(source,tmp_path/'all')
    assert _load_yaml_string(generate_dsl_string(rebuild_workflow(out)))==raw
    assert len({node.data.type for node in source.nodes})==len(types)


def test_in_place_edit_code_prompt_and_unknown_fields_in_split(tmp_path):
    source=_load_yaml(EXTERNAL_CASES[1])
    dsl=DifyDSL.model_validate(deepcopy(source))
    folder=split_workflow(dsl,tmp_path/'editable')
    code=next(folder.glob('nodes/code/*/code.py'))
    code.write_text(code.read_text(encoding='utf-8')+'\n# 修改代码后应写回 DSL\n',encoding='utf-8')
    output=rebuild_workflow(folder)
    assert any('# 修改代码后应写回 DSL' in n.data.code for n in output.nodes if n.data.type=='code')
    assert len(output.nodes)==len(dsl.nodes)

@pytest.mark.parametrize('official', OFFICIAL_CASES, ids=lambda p: p.stem)
def test_official_fixture_passes_structural_validator(official):
    from dify_dsl.validator import validate
    result=validate(DifyDSL.model_validate(deepcopy(_load_yaml(official))))
    assert result.is_valid, result.errors


def test_advanced_workflow_edits_propagate_both_directions(tmp_path):
    """非空真实业务图：修改复杂的 LLM 模型配置和任意未来未知字段。"""
    p=EXTERNAL_CASES[1]
    source=_load_yaml(p)
    yaml_path=tmp_path/'workflow.yml'
    py_path=tmp_path/'workflow.py'
    yaml_path.write_text(generate_dsl_string(DifyDSL.model_validate(deepcopy(source))),encoding='utf-8')
    assert sync_pair(yaml_path,py_path)=='yaml-to-python'
    py=py_path.read_text(encoding='utf-8')
    assert "'max_tokens': 131072" in py
    py_path.write_text(py.replace("'max_tokens': 131072","'max_tokens': 65536",1),encoding='utf-8')
    assert sync_pair(yaml_path,py_path)=='python-to-yaml'
    changed=_load_yaml(yaml_path)
    new_limits=[n['data']['model']['completion_params']['max_tokens'] for n in changed['workflow']['graph']['nodes'] if n['data']['type']=='llm']
    assert new_limits.count(65536)==1
    assert new_limits.count(131072)==5
    assert sync_pair(yaml_path,py_path)=='unchanged'
