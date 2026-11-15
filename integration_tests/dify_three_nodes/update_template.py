"""只更新独立测试模板 App；保留原始样例和原有业务 App。"""
from pathlib import Path
from app_factory import create_app
from sqlalchemy import select
_,app=create_app()
with app.app_context():
 from extensions.ext_database import db
 from models import App, Account
 from services.app_dsl_service import AppDslService
 from services.workflow_service import WorkflowService
 tenant='21483624-531f-45b9-850b-597e2162c0ce'
 app_id='a752618f-4dbc-40f4-adad-33f3a9aa0de7'
 account=db.session.scalars(select(Account)).first()
 account.set_tenant_id_with_session(tenant,session=db.session)
 content=Path('/tmp/dify-e2e-template-revised.yml').read_text(encoding='utf-8')
 result=AppDslService(db.session).import_app(account=account,import_mode='yaml-content',yaml_content=content,app_id=app_id)
 print('REVISED_IMPORT',result.status,str(result.error)[:350],'WARNINGS',[(w.model_dump() if hasattr(w,'model_dump') else str(w)) for w in (result.warnings or [])],flush=True)
 assert 'completed' in str(result.status)
 model=db.session.scalar(select(App).where(App.id==app_id))
 workflow=WorkflowService().publish_workflow(session=db.session,app_model=model,account=account)
 model.workflow_id=workflow.id
 db.session.commit()
 print('REVISED_PUBLISHED',model.id,workflow.id,flush=True)
