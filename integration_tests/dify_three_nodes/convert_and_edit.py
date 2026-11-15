"""实际走 CLI YAML→Python，在 Python 声明中修改真实节点字段，随后 Python→YAML。"""
import ast
import pprint
import subprocess
import sys
from pathlib import Path
from dify_dsl.parser import _load_yaml

HERE=Path(__file__).parent

def run(*args):
    output=subprocess.run([sys.executable,'-m','dify_dsl',*map(str,args)],capture_output=True,text=True)
    if output.returncode:raise RuntimeError(f'cmd={args}: {output.stdout} {output.stderr}')
    print('CLI',args[0],output.stdout.strip())

for kind in ['template','loop','assigner']:
    initial=HERE/(kind+'.source.yml')
    as_python=HERE/(kind+'.py')
    result=HERE/(kind+'.deploy.yml')
    run('to-python',initial,'-o',as_python,'--force')
    tree=ast.parse(as_python.read_text(encoding='utf-8'))
    source=ast.literal_eval(tree.body[0].value)
    graph=source['workflow']['graph']
    if kind=='template':
        tmpl=next(n for n in graph['nodes'] if n['data']['type']=='template-transform')
        tmpl['data']['template']='已优化：{{ arg1 | upper }}'
    elif kind=='loop':
        loop=next(n for n in graph['nodes'] if n['data']['type']=='loop')
        loop['data']['break_conditions'][0]['value']='7'
    else:
        assign=next(n for n in graph['nodes'] if n['data']['type']=='assigner')
        assign['data']['items'][0]['value']=2
    as_python.write_text('# 修改后的 Dify Workflow Python 声明；由 ast.literal_eval 安全解析。\nWORKFLOW_DSL = '+pprint.pformat(source,width=100,sort_dicts=False)+'\n',encoding='utf-8')
    run('from-python',as_python,'-o',result,'--force')
    run('validate',result)
    actual=_load_yaml(result)
    assert actual==source,(kind,'Python->YAML lost fields')
    check=HERE/(kind+'.roundtrip.py')
    run('to-python',result,'-o',check,'--force')
    assert ast.literal_eval(ast.parse(check.read_text()).body[0].value)==source
    check.unlink()
    print('ROUNDTRIP_OK',kind,'NODES',len(graph['nodes']))
