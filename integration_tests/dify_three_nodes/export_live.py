"""只读导出隔离测试 App 的发布版 Dify DSL，进行真实导出往返验证。"""
from pathlib import Path
from app_factory import create_app
from sqlalchemy import select

APPS={'template':'a752618f-4dbc-40f4-adad-33f3a9aa0de7',
      'loop':'28878b4e-c9d6-4ab9-935e-92b285c34b1e',
      'assigner':'1d11c335-34fe-49e5-b9ca-cf838b29a9ef'}
_,app=create_app()
with app.app_context():
    from extensions.ext_database import db
    from models import App
    from services.app_dsl_service import AppDslService
    for name,app_id in APPS.items():
        model=db.session.scalar(select(App).where(App.id==app_id))
        assert model
        text=AppDslService.export_dsl(model,session=db.session,workflow_id=model.workflow_id)
        path=Path('/tmp/dify-e2e-'+name+'-server-export.yml')
        path.write_text(text,encoding='utf-8')
        print('EXPORTED',name,'BYTES',len(text),'WORKFLOW',model.workflow_id,flush=True)
