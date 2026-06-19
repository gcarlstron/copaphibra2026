from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal, get_db
from app.models import Usuario
from app.services.auth import verificar_senha
from app.services.sync_resultados import disparar_sync_se_necessario

router = APIRouter()


def get_current_user(request: Request, db: Session = Depends(get_db)) -> Usuario | None:
    usuario_id = request.session.get("user_id")
    if usuario_id is None:
        return None

    return db.get(Usuario, usuario_id)


def get_current_admin(current_user: Usuario | None = Depends(get_current_user)) -> Usuario:
    if current_user is None or not current_user.ativo or not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso restrito")
    return current_user


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request) -> HTMLResponse:
    settings = get_settings()
    templates = Jinja2Templates(directory=str(settings.templates_dir))
    return templates.TemplateResponse(request, "login.html", {"app_name": settings.app_name})


@router.post("/login")
def login(
    request: Request,
    background_tasks: BackgroundTasks,
    username: str = Form(...),
    senha: str = Form(...),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    stmt = select(Usuario).where(Usuario.username == username)
    usuario = db.scalar(stmt)

    if usuario is None or not usuario.ativo or not verificar_senha(senha, usuario.senha_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciais inválidas")

    request.session["user_id"] = usuario.id

    # Dispara sync de resultados ESPN em background — não bloqueia a resposta.
    # A sessão do Depends(get_db) estará fechada quando a task rodar;
    # por isso a task abre sua própria sessão via SessionLocal.
    background_tasks.add_task(
        disparar_sync_se_necessario,
        SessionLocal,
        datetime.now(timezone.utc),
    )

    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    return response


@router.post("/logout")
def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
