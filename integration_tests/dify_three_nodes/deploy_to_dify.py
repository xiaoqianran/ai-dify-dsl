"""仅创建隔离的 E2E 测试应用，不覆盖现有 Dify 用户工作流。"""
from pathlib import Path
from app_factory import create_app
from sqlalchemy import select
import json

_,app=create_app()
with app.app_context():
    from extensions.ext_database import db
    from models import App,Account
    from services.app_dsl_service import AppDslService
    from services.workflow_service import WorkflowService
    owner=db.session.scalars(select(Account)).first()
    tenant='21483624-531f-45b9-850b-597e2162c0ce'
    owner.set_tenant_id_with_session(tenant,session=db.session)
    results={}
    for kind in ['template','loop','assigner']:
        name='ai-dify-dsl E2E '+kind
        existing=db.session.scalar(select(App).where(App.tenant_id==tenant,App.name==name))
        if existing is not None:
            print('APP_EXISTS',kind,existing.id,flush=True)
            model=existing
            result=AppDslService(db.session).import_app(account=owner,import_mode='yaml-content',yaml_content=Path('/tmp/dify-e2e-'+kind+'.yml').read_text(),app_id=existing.id)
        else:
            result=AppDslService(db.session).import_app(account=owner,import_mode='yaml-content',yaml_content=Path('/tmp/dify-e2e-'+kind+'.yml').read_text())
            if not result.app_id:
                print('IMPORT_FAILED',kind,result.status,result.error,flush=True)
                raise RuntimeError('Cannot import '+kind)
            model=db.session.scalar(select(App).where(App.id==result.app_id))
        print('IMPORT',kind,result.status,'APP',model.id,'ERROR',str(result.error)[:250],flush=True)
        if 'completed' not in str(result.status):
            raise RuntimeError('Dify import '+kind+' '+str(result.status)+' '+str(result.error))
        workflow=WorkflowService().publish_workflow(session=db.session,app_model=model,account=owner)
        model.workflow_id=workflow.id
        db.session.commit()
        print('PUBLISHED',kind,workflow.id,model.id,flush=True)
        results[kind]={'app_id':model.id,'workflow_id':workflow.id,'import_status':str(result.status)}
    print('E2E_APPS',json.dumps(results),flush=True)
