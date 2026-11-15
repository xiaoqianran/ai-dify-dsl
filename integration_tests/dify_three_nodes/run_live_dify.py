"""实际调用 Dify Service API 执行三种节点，临时 API Token 在 finally 中回收。"""
import json
import requests
from app_factory import create_app
from sqlalchemy import select

APPS={
 'template':('a752618f-4dbc-40f4-adad-33f3a9aa0de7',{'query':'hello dify'}, {'result':'已复核：HELLO DIFY'}),
 'loop':('28878b4e-c9d6-4ab9-935e-92b285c34b1e',{}, {'num':7}),
 'assigner':('1d11c335-34fe-49e5-b9ca-cf838b29a9ef',{}, {'num':5}),
}
_,app=create_app()
with app.app_context():
 from extensions.ext_database import db
 from extensions.ext_application_services import application_services
 from machinery.context import RequestContext
 from models import Account
 account=db.session.scalars(select(Account)).first()
 tenant='21483624-531f-45b9-850b-597e2162c0ce'
 account.set_tenant_id_with_session(tenant,session=db.session)
 outcomes={}
 for kind,(app_id,inputs,expected) in APPS.items():
  context=RequestContext('ai-dify-dsl-e2e-'+kind,None,account.id,tenant)
  key=application_services().app_api_keys.create_key(context,app_id)
  try:
   resp=requests.post('http://nginx/v1/workflows/run',json={'inputs':inputs,'response_mode':'blocking','user':'ai-dify-dsl-e2e'},headers={'Authorization':'Bearer '+key.token},timeout=180)
   print('HTTP',kind,resp.status_code,flush=True)
   try:payload=resp.json()
   except Exception:payload={'body_preview':resp.text[:400]}
   data=payload.get('data') or {}
   actual=data.get('outputs') or {}
   info={'http':resp.status_code,'status':data.get('status'),'run_id':data.get('workflow_run_id') or payload.get('workflow_run_id'),'error':data.get('error'),'outputs':actual,'expected':expected}
   info['match']=resp.status_code==200 and data.get('status')=='succeeded' and all(actual.get(k)==v for k,v in expected.items())
   outcomes[kind]=info
   print('RESULT',kind,json.dumps(info,ensure_ascii=False)[:1700],flush=True)
  finally:
   application_services().app_api_keys.delete_key(context,app_id,key.id)
   print('KEY_REVOKED',kind,flush=True)
 print('SUMMARY',json.dumps({k:v['match'] for k,v in outcomes.items()}),flush=True)
 if not all(v['match'] for v in outcomes.values()):raise RuntimeError('One or more real Dify executions failed')
