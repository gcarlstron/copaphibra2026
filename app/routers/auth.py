from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import Usuario
from app.services.auth import alterar_senha, verificar_senha

router = APIRouter()


def _templates() -> Jinja2Templates:
    settings = get_settings()
    return Jinja2Templates(directory=str(settings.templates_dir))


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
    return _templates().TemplateResponse(request, "login.html", {"app_name": settings.app_name})


@router.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    senha: str = Form(...),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    stmt = select(Usuario).where(Usuario.username == username)
    usuario = db.scalar(stmt)

    if usuario is None or not usuario.ativo or not verificar_senha(senha, usuario.senha_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciais inválidas")

    request.session["user_id"] = usuario.id

    # O sync de resultados ESPN é disparado ao carregar o dashboard (GET /),
    # não mais no login — ver app/routers/dashboard.py.
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/logout")
def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/trocar-senha", response_class=HTMLResponse)
def trocar_senha_form(
    request: Request,
    current_user: Usuario | None = Depends(get_current_user),
) -> Response:
    if current_user is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    settings = get_settings()
    return _templates().TemplateResponse(
        request,
        "trocar_senha.html",
        {
            "app_name": settings.app_name,
            "user_id": current_user.id,
            "is_admin": current_user.is_admin,
        },
    )


@router.post("/trocar-senha", response_class=HTMLResponse)
def trocar_senha(
    request: Request,
    senha_atual: str = Form(...),
    nova_senha: str = Form(...),
    confirmacao: str = Form(...),
    db: Session = Depends(get_db),
    current_user: Usuario | None = Depends(get_current_user),
) -> Response:
    if current_user is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    settings = get_settings()
    contexto: dict[str, object] = {
        "app_name": settings.app_name,
        "user_id": current_user.id,
        "is_admin": current_user.is_admin,
    }

    try:
        alterar_senha(
            db=db,
            usuario=current_user,
            senha_atual=senha_atual,
            nova_senha=nova_senha,
            confirmacao=confirmacao,
        )
    except ValueError as exc:
        contexto["erro"] = str(exc)
        return _templates().TemplateResponse(
            request,
            "trocar_senha.html",
            contexto,
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    contexto["sucesso"] = True
    return _templates().TemplateResponse(request, "trocar_senha.html", contexto)
