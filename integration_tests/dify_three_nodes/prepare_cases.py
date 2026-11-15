"""只从 Dify API 容器自带官方 DSL 派生独立测试 App，不覆盖用户生产工作流。"""
from copy import deepcopy
from pathlib import Path
from dify_dsl import DifyDSL, generate_dsl_string
from dify_dsl.parser import _load_yaml

HERE=Path(__file__).parent
OFFICIAL=Path('/tmp/dify-node-fixtures')

def read(name):
    return _load_yaml(OFFICIAL/(name+'.yml'))

def save(name, data):
    data['app']['name']='ai-dify-dsl E2E '+name
    data['app']['description']='独立集成测试，不修改现有业务 App；上游 Dify 官方样例衍生。'
    (HERE/(name+'.source.yml')).write_text(generate_dsl_string(DifyDSL.model_validate(data)),encoding='utf-8')
    print('PREPARED',name,len(data['workflow']['graph']['nodes']),len(data['workflow']['graph']['edges']))

# 1. 模板转换：Start -> Template -> End，无模型和外部网络依赖。
base=read('simple_passthrough_workflow')
node_start=next(x for x in base['workflow']['graph']['nodes'] if x['data']['type']=='start')
node_end=next(x for x in base['workflow']['graph']['nodes'] if x['data']['type']=='end')
tmpl=deepcopy(next(x for x in read('array_iteration_formatting_workflow')['workflow']['graph']['nodes'] if x['data']['type']=='template-transform'))
startid=node_start['id'];tid=tmpl['id'];eid=node_end['id']
for field in ('parentId','extent'):
    tmpl.pop(field,None)
tmpl['data'].pop('iteration_id',None)
tmpl['data']['isInIteration']=False
tmpl['data']['variables']=[{'variable':'arg1','value_type':'string','value_selector':[startid,'query']}]
node_end['data']['outputs']=[{'variable':'result','value_type':'string','value_selector':[tid,'output']}]
base['workflow']['graph']['nodes']=[node_start,tmpl,node_end]
base['workflow']['graph']['edges']=[
    {'id':'start-template','source':startid,'target':tid,'sourceHandle':'source','targetHandle':'target','type':'custom','data':{'sourceType':'start','targetType':'template-transform'}},
    {'id':'template-end','source':tid,'target':eid,'sourceHandle':'source','targetHandle':'target','type':'custom','data':{'sourceType':'template-transform','targetType':'end'}}]
node_start['data']['variables']=[{'variable':'query','label':'query','type':'text-input','required':True,'max_length':512}]
save('template',base)

# 2. 循环入口：使用 Dify 自己的 loop-start + assigner 嵌套样例。
base=read('increment_loop_with_break_condition_workflow')
save('loop',base)

# 3. 赋值：同样使用真实循环容器进行赋值运算，避免无法写入的只读变量。
base=read('increment_loop_with_break_condition_workflow')
save('assigner',base)
