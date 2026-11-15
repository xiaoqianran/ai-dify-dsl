"""测试经过独立 template.txt 外置编辑后重建、双向转换仍能真实部署。"""
import ast
import subprocess
import sys
from pathlib import Path
from dify_dsl import parse_dsl,generate_dsl_string
from dify_dsl.splitter import split_workflow
from dify_dsl.rebuilder import rebuild_workflow
from dify_dsl.parser import _load_yaml,_load_yaml_string

root=Path(__file__).parent
src=root/'template.deploy.yml'
folder=root/'template.split'
split_workflow(parse_dsl(src),folder)
file=next((folder/'nodes'/'template-transform').glob('*/template.txt'))
old=file.read_text(encoding='utf-8')
assert old=='已优化：{{ arg1 | upper }}',repr(old)
file.write_text('已复核：{{ arg1 | upper }}',encoding='utf-8')
rebuilt=rebuild_workflow(folder)
template=next(n for n in rebuilt.nodes if n.data.type=='template-transform')
assert template.data.template=='已复核：{{ arg1 | upper }}'
rebuilt_yaml=root/'template.revised.yml'
rebuilt_yaml.write_text(generate_dsl_string(rebuilt),encoding='utf-8')
py_path=root/'template.revised.py'
final=root/'template.revised.deploy.yml'
for cmd in [['to-python',str(rebuilt_yaml),'-o',str(py_path),'--force'],['from-python',str(py_path),'-o',str(final),'--force'],['compare',str(rebuilt_yaml),str(final)]]:
 p=subprocess.run([sys.executable,'-m','dify_dsl',*cmd],capture_output=True,text=True)
 assert p.returncode==0,(cmd,p.stdout,p.stderr)
 print('CLI',cmd[0],p.stdout.strip())
assert _load_yaml(final)==_load_yaml(rebuilt_yaml)
print('REVISED_TEMPLATE_READY',final)
