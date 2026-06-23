"""Admin router — manages rounds, games and users.

Authorization (Decision D6):
  - Anonymous request  → 303 redirect to /login
  - Authenticated non-admin → 403 Forbidden
  - Authenticated admin    → full access

We achieve this by taking get_current_user (which returns None for anonymous)
and checking is_admin manually in every route rather than using get_current_admin
(which raises 403 for both cases).  This preserves the original behaviour of
get_current_admin for other callers while satisfying the distinct redirect rule.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import Usuario
from app.routers.auth import get_current_user
from app.services import admin as admin_svc

router = APIRouter(prefix="/admin")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _templates() -> Jinja2Templates:
    settings = get_settings()
    templates = Jinja2Templates(directory=str(settings.templates_dir))
    templates.env.globals["asset_version"] = settings.asset_version
    return templates


def _check_admin(current_user: Usuario | None) -> Usuario | RedirectResponse:
    """Returns the admin Usuario, or a redirect/403 response to short-circuit."""
    if current_user is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    if not current_user.ativo or not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso restrito a administradores.")
    return current_user


def _redirect_or_htmx(request: Request, url: str) -> Response:
    if request.headers.get("HX-Request") == "true":
        return Response(status_code=status.HTTP_204_NO_CONTENT, headers={"HX-Redirect": url})
    return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)


# ---------------------------------------------------------------------------
# Rodadas
# ---------------------------------------------------------------------------


@router.get("/rodadas", response_class=HTMLResponse)
def listar_rodadas(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario | None = Depends(get_current_user),
) -> Response:
    guard = _check_admin(current_user)
    if isinstance(guard, Response):
        return guard

    settings = get_settings()
    rodadas = admin_svc.listar_rodadas(db)
    return _templates().TemplateResponse(
        request,
        "admin/rodadas.html",
        {
            "app_name": settings.app_name,
            "user_id": guard.id,
            "is_admin": True,
            "rodadas": rodadas,
            "erro": None,
        },
    )


@router.post("/rodadas")
def criar_rodada(
    request: Request,
    nome: str = Form(...),
    ordem: int = Form(...),
    db: Session = Depends(get_db),
    current_user: Usuario | None = Depends(get_current_user),
) -> Response:
    guard = _check_admin(current_user)
    if isinstance(guard, Response):
        return guard

    try:
        admin_svc.criar_rodada(db, nome=nome, ordem=ordem)
    except ValueError as exc:
        settings = get_settings()
        rodadas = admin_svc.listar_rodadas(db)
        return _templates().TemplateResponse(
            request,
            "admin/rodadas.html",
            {
                "app_name": settings.app_name,
                "user_id": guard.id,
                "is_admin": True,
                "rodadas": rodadas,
                "erro": str(exc),
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    return _redirect_or_htmx(request, "/admin/rodadas")


@router.post("/rodadas/{rodada_id}")
def atualizar_rodada(
    request: Request,
    rodada_id: int,
    aberta: bool = Form(False),
    abertura: str = Form(""),
    fechamento: str = Form(""),
    db: Session = Depends(get_db),
    current_user: Usuario | None = Depends(get_current_user),
) -> Response:
    guard = _check_admin(current_user)
    if isinstance(guard, Response):
        return guard

    def _parse_dt(value: str) -> datetime | None:
        value = value.strip()
        if not value:
            return None
        # Accept ISO format with or without timezone.
        for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                dt = datetime.strptime(value, fmt)
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        raise ValueError(f"Formato de data inválido: '{value}'. Use YYYY-MM-DDTHH:MM.")

    try:
        abertura_dt = _parse_dt(abertura)
        fechamento_dt = _parse_dt(fechamento)
        admin_svc.atualizar_rodada(db, rodada_id=rodada_id, aberta=aberta, abertura=abertura_dt, fechamento=fechamento_dt)
    except ValueError as exc:
        msg = str(exc)
        http_status = (
            status.HTTP_404_NOT_FOUND
            if "não encontrada" in msg
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=http_status, detail=msg) from exc

    return _redirect_or_htmx(request, "/admin/rodadas")


# ---------------------------------------------------------------------------
# Jogos
# ---------------------------------------------------------------------------


@router.get("/jogos", response_class=HTMLResponse)
def listar_jogos(
    request: Request,
    rodada_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: Usuario | None = Depends(get_current_user),
) -> Response:
    guard = _check_admin(current_user)
    if isinstance(guard, Response):
        return guard

    settings = get_settings()
    jogos = admin_svc.listar_jogos(db, rodada_id=rodada_id)
    rodadas = admin_svc.listar_rodadas(db)
    return _templates().TemplateResponse(
        request,
        "admin/jogos.html",
        {
            "app_name": settings.app_name,
            "user_id": guard.id,
            "is_admin": True,
            "jogos": jogos,
            "rodadas": rodadas,
            "rodada_id_filtro": rodada_id,
            "erro": None,
        },
    )


@router.post("/jogos")
def criar_jogo(
    request: Request,
    rodada_id: int = Form(...),
    data_hora: str = Form(...),
    time_casa: str = Form(...),
    time_visitante: str = Form(...),
    db: Session = Depends(get_db),
    current_user: Usuario | None = Depends(get_current_user),
) -> Response:
    guard = _check_admin(current_user)
    if isinstance(guard, Response):
        return guard

    try:
        dt = _parse_data_hora(data_hora)
        admin_svc.criar_jogo(db, rodada_id=rodada_id, data_hora=dt, time_casa=time_casa, time_visitante=time_visitante)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return _redirect_or_htmx(request, "/admin/jogos")


@router.post("/jogos/{jogo_id}")
def atualizar_jogo(
    request: Request,
    jogo_id: int,
    data_hora: str = Form(...),
    time_casa: str = Form(...),
    time_visitante: str = Form(...),
    db: Session = Depends(get_db),
    current_user: Usuario | None = Depends(get_current_user),
) -> Response:
    guard = _check_admin(current_user)
    if isinstance(guard, Response):
        return guard

    try:
        dt = _parse_data_hora(data_hora)
        admin_svc.atualizar_jogo(db, jogo_id=jogo_id, data_hora=dt, time_casa=time_casa, time_visitante=time_visitante)
    except ValueError as exc:
        msg = str(exc)
        http_status = (
            status.HTTP_404_NOT_FOUND
            if "não encontrad" in msg
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=http_status, detail=msg) from exc

    return _redirect_or_htmx(request, "/admin/jogos")


@router.post("/jogos/{jogo_id}/resultado")
def lancar_resultado(
    request: Request,
    jogo_id: int,
    gols_casa: int = Form(...),
    gols_visitante: int = Form(...),
    db: Session = Depends(get_db),
    current_user: Usuario | None = Depends(get_current_user),
) -> Response:
    guard = _check_admin(current_user)
    if isinstance(guard, Response):
        return guard

    try:
        admin_svc.lancar_resultado(db, jogo_id=jogo_id, gols_casa=gols_casa, gols_visitante=gols_visitante)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return _redirect_or_htmx(request, "/admin/jogos")


# ---------------------------------------------------------------------------
# Usuarios
# ---------------------------------------------------------------------------


@router.get("/usuarios", response_class=HTMLResponse)
def listar_usuarios(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario | None = Depends(get_current_user),
) -> Response:
    guard = _check_admin(current_user)
    if isinstance(guard, Response):
        return guard

    settings = get_settings()
    usuarios = admin_svc.listar_usuarios(db)
    return _templates().TemplateResponse(
        request,
        "admin/usuarios.html",
        {
            "app_name": settings.app_name,
            "user_id": guard.id,
            "is_admin": True,
            "usuarios": usuarios,
            "erro": None,
        },
    )


@router.post("/usuarios")
def criar_usuario(
    request: Request,
    nome: str = Form(...),
    username: str = Form(...),
    senha: str = Form(...),
    is_admin: bool = Form(False),
    db: Session = Depends(get_db),
    current_user: Usuario | None = Depends(get_current_user),
) -> Response:
    guard = _check_admin(current_user)
    if isinstance(guard, Response):
        return guard

    try:
        admin_svc.criar_usuario(db, nome=nome, username=username, senha=senha, is_admin=is_admin)
    except ValueError as exc:
        settings = get_settings()
        usuarios = admin_svc.listar_usuarios(db)
        return _templates().TemplateResponse(
            request,
            "admin/usuarios.html",
            {
                "app_name": settings.app_name,
                "user_id": guard.id,
                "is_admin": True,
                "usuarios": usuarios,
                "erro": str(exc),
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    return _redirect_or_htmx(request, "/admin/usuarios")


@router.post("/usuarios/{usuario_id}/senha")
def resetar_senha(
    request: Request,
    usuario_id: int,
    nova_senha: str = Form(...),
    db: Session = Depends(get_db),
    current_user: Usuario | None = Depends(get_current_user),
) -> Response:
    guard = _check_admin(current_user)
    if isinstance(guard, Response):
        return guard

    try:
        admin_svc.resetar_senha(db, usuario_id=usuario_id, nova_senha=nova_senha)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return _redirect_or_htmx(request, "/admin/usuarios")


@router.post("/usuarios/{usuario_id}/ativo")
def definir_ativo(
    request: Request,
    usuario_id: int,
    ativo: bool = Form(...),
    db: Session = Depends(get_db),
    current_user: Usuario | None = Depends(get_current_user),
) -> Response:
    guard = _check_admin(current_user)
    if isinstance(guard, Response):
        return guard

    try:
        admin_svc.definir_ativo(db, usuario_id=usuario_id, ativo=ativo)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return _redirect_or_htmx(request, "/admin/usuarios")


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------


def _parse_data_hora(value: str) -> datetime:
    """Parses a datetime string from an HTML datetime-local input."""
    value = value.strip()
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            dt = datetime.strptime(value, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise ValueError(f"Formato de data/hora inválido: '{value}'. Use YYYY-MM-DDTHH:MM.")
