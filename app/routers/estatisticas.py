from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app.config import get_settings
from app.routers.auth import get_current_user
from app.services.estatisticas import PAINEL_GERAL_URL, painel_do_jogador
from app.templating import get_templates as _templates

router = APIRouter()


@router.get("/estatisticas", response_class=HTMLResponse)
def estatisticas(
    request: Request,
    current_user=Depends(get_current_user),
) -> Response:
    if current_user is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    settings = get_settings()
    templates = _templates()
    return templates.TemplateResponse(
        request,
        "estatisticas.html",
        {
            "app_name": settings.app_name,
            "user_id": current_user.id,
            "is_admin": current_user.is_admin,
            "nome_usuario": current_user.nome,
            "painel_geral_url": PAINEL_GERAL_URL,
            "painel_usuario_url": painel_do_jogador(current_user.nome),
        },
    )
