from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal, get_db
from app.routers.auth import get_current_user
from app.services.dashboard import montar_dashboard
from app.services.sync_resultados import disparar_sync_se_necessario

router = APIRouter()


def _templates() -> Jinja2Templates:
    settings = get_settings()
    return Jinja2Templates(directory=str(settings.templates_dir))


@router.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> Response:
    if current_user is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    # Dispara o sync de resultados ESPN em background ao carregar o dashboard —
    # não bloqueia a resposta. O throttle persistido (SyncState) evita martelar a
    # ESPN a cada refresh. A sessão do Depends(get_db) estará fechada quando a task
    # rodar; por isso a task abre sua própria sessão via SessionLocal.
    background_tasks.add_task(
        disparar_sync_se_necessario,
        SessionLocal,
        datetime.now(timezone.utc),
    )

    settings = get_settings()
    templates = _templates()
    dados = montar_dashboard(db, agora=datetime.now(timezone.utc))

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "app_name": settings.app_name,
            "user_id": current_user.id,
            "is_admin": current_user.is_admin,
            "dados": dados,
            "auto_refresh_s": settings.auto_refresh_ao_vivo_s if dados.jogos_ao_vivo else None,
        },
    )
