"""只读核验 Dify 运行后的节点执行日志和发布图配置。"""
import json
from app_factory import create_app
from sqlalchemy import text
APPS={'template':('a752618f-4dbc-40f4-adad-33f3a9aa0de7','cea16b57-d4f8-403f-9629-2cec2cdb5593'),
      'loop':('28878b4e-c9d6-4ab9-935e-92b285c34b1e','cadd282a-356c-40c1-8d61-2c2ab9843bba'),
      'assigner':('1d11c335-34fe-49e5-b9ca-cf838b29a9ef','9efbd6d7-772d-4e25-858c-7befb2c29b0d')}
_,app=create_app()
with app.app_context():
 from extensions.ext_database import db
 for kind,(appid,runid) in APPS.items():
  wf=db.session.execute(text('SELECT workflow_id FROM apps WHERE id=:appid'),{'appid':appid}).scalar()
  assert wf
  graph=db.session.execute(text('SELECT graph FROM workflows WHERE id=:wf'),{'wf':wf}).scalar()
  if isinstance(graph,str):graph=json.loads(graph)
  kinds=[n['data']['type'] for n in graph['nodes']]
  target='template-transform' if kind=='template' else 'loop-start' if kind=='loop' else 'assigner'
  assert target in kinds
  result=db.session.execute(text('SELECT status,outputs,error FROM workflow_runs WHERE id=:rid'),{'rid':runid}).first()
  print('RUN',kind,result[0],'nodes',kinds,'outputs',str(result[1])[:300],'error',result[2],flush=True)
  execution=db.session.execute(text('SELECT node_id,title,status,outputs,error FROM workflow_node_executions WHERE workflow_run_id=:rid ORDER BY created_at'),{'rid':runid}).all()
  for nid,title,status,outputs,error in execution:
   out=json.loads(outputs) if isinstance(outputs,str) else outputs or {}
   print(' EXEC',kind,nid,title,status,'outputs',str(out)[:350],'error',str(error)[:130],flush=True)
  print('EXEC_COUNT',kind,len(execution),flush=True)
