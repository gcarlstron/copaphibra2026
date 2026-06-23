from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings
from app.routers.admin import router as admin_router
from app.routers.auth import router as auth_router
from app.routers.dashboard import router as dashboard_router
from app.routers.estatisticas import router as estatisticas_router
from app.routers.jogos import router as jogos_router
from app.routers.palpites import router as palpites_router


def create_app() -> FastAPI:
    settings = get_settings()

    if not settings.debug and settings.secret_key in ("", "dev-secret-change-me"):
        raise RuntimeError(
            "SECRET_KEY inseguro/ausente: defina a variável de ambiente SECRET_KEY antes de subir em produção (DEBUG desligado)."
        )

    app = FastAPI(title=settings.app_name, debug=settings.debug)

    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        same_site="lax",
        https_only=settings.session_https_only,
        max_age=60 * 60 * 24 * 14,  # 14 dias
    )
    app.mount("/static", StaticFiles(directory=str(settings.static_dir)), name="static")
    app.include_router(auth_router)
    app.include_router(palpites_router)
    app.include_router(jogos_router)
    app.include_router(dashboard_router)
    app.include_router(estatisticas_router)
    app.include_router(admin_router)

    @app.get("/healthz")
    def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
