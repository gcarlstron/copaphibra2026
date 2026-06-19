from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.routers.auth import get_current_user
from app.services.dashboard import STATUS_AO_VIVO
from app.services.jogos import detalhe_do_jogo, listar_todos_os_jogos

router = APIRouter(prefix="/jogos")


def _templates() -> Jinja2Templates:
    settings = get_settings()
    return Jinja2Templates(directory=str(settings.templates_dir))


@router.get("", response_class=HTMLResponse)
def jogos_lista(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> Response:
    """Lista todos os jogos agrupados por rodada com os pontos do próprio usuário."""
    if current_user is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    dados = listar_todos_os_jogos(db=db, usuario=current_user)

    settings = get_settings()
    tem_ao_vivo = any(
        j.status in STATUS_AO_VIVO for grupo in dados.grupos for j in grupo.jogos
    )
    templates = _templates()
    return templates.TemplateResponse(
        request,
        "jogos_lista.html",
        {
            "app_name": settings.app_name,
            "user_id": current_user.id,
            "is_admin": current_user.is_admin,
            "dados": dados,
            "auto_refresh_s": settings.auto_refresh_ao_vivo_s if tem_ao_vivo else None,
        },
    )


@router.get("/{jogo_id}", response_class=HTMLResponse)
def jogo_detalhe(
    jogo_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> Response:
    if current_user is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    try:
        dados = detalhe_do_jogo(
            db=db,
            jogo_id=jogo_id,
            usuario=current_user,
            agora=datetime.now(timezone.utc),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    settings = get_settings()
    templates = _templates()
    return templates.TemplateResponse(
        request,
        "jogo_detalhe.html",
        {
            "app_name": settings.app_name,
            "user_id": current_user.id,
            "is_admin": current_user.is_admin,
            "dados": dados,
            "auto_refresh_s": (
                settings.auto_refresh_ao_vivo_s
                if dados.jogo.status in STATUS_AO_VIVO
                else None
            ),
        },
    )
