from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.routers.auth import get_current_user
from app.services.dashboard import montar_dashboard
from app.services.sync_resultados import sincronizar_se_necessario

logger = logging.getLogger(__name__)

router = APIRouter()


def _templates() -> Jinja2Templates:
    settings = get_settings()
    templates = Jinja2Templates(directory=str(settings.templates_dir))
    templates.env.globals["asset_version"] = settings.asset_version
    return templates


@router.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> Response:
    if current_user is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    settings = get_settings()

    # Sincroniza os resultados da ESPN ANTES de renderizar, na própria sessão do
    # request, para que a classificação/jogos já saiam atualizados na 1ª carga
    # (sem precisar de F5). O throttle persistido (SyncState) faz a maioria dos
    # acessos pular o fetch; só o 1º de cada janela de ~15 min realmente bate na
    # ESPN. O `deadline` limita o tempo de espera, e o try/except garante que,
    # se a ESPN estiver lenta/fora, a página renderiza com os dados do banco.
    deadline = time.monotonic() + settings.espn_sync_deadline_s
    try:
        sincronizar_se_necessario(db, datetime.now(timezone.utc), deadline=deadline)
    except Exception:
        logger.exception(
            "Sync ESPN síncrono falhou; renderizando o dashboard com os dados existentes."
        )

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
