from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.routers.auth import get_current_user
from app.services.palpites import listar_palpites_do_usuario, salvar_palpite
from app.services.tempo import agora as agora_dados

router = APIRouter(prefix="/palpites")


def _templates() -> Jinja2Templates:
    settings = get_settings()
    templates = Jinja2Templates(directory=str(settings.templates_dir))
    templates.env.globals["asset_version"] = settings.asset_version
    return templates


@router.get("", response_class=HTMLResponse)
def meus_palpites(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> Response:
    if current_user is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    settings = get_settings()
    templates = _templates()
    rodadas = listar_palpites_do_usuario(db, current_user)
    return templates.TemplateResponse(
        request,
        "palpites.html",
        {
            "app_name": settings.app_name,
            "user_id": current_user.id,
            "rodadas": rodadas,
        },
    )


@router.post("/{jogo_id}")
def salvar_meu_palpite(
    request: Request,
    jogo_id: int,
    gols_casa: int = Form(...),
    gols_visitante: int = Form(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> Response:
    if current_user is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    try:
        salvar_palpite(
            db=db,
            usuario=current_user,
            jogo_id=jogo_id,
            gols_casa=gols_casa,
            gols_visitante=gols_visitante,
            agora=agora_dados(),
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    if request.headers.get("HX-Request") == "true":
        return Response(status_code=status.HTTP_204_NO_CONTENT, headers={"HX-Redirect": "/palpites"})

    return RedirectResponse(url="/palpites", status_code=status.HTTP_303_SEE_OTHER)
