"""Instância única de Jinja2Templates compartilhada pelos routers.

Antes cada router definia o seu próprio `_templates()` (5 cópias) e criava um
`Jinja2Templates` novo a cada request. Aqui há uma **única** instância (que
preserva o cache de templates do Jinja) e o global `asset_version` é atualizado
a cada chamada — mantendo o cache-busting dinâmico em dev (muda com o mtime de
`app.css`/`ui.js`) e estável em produção (commit do deploy).
"""

from __future__ import annotations

from fastapi.templating import Jinja2Templates

from app.config import get_settings

_templates = Jinja2Templates(directory=str(get_settings().templates_dir))


def get_templates() -> Jinja2Templates:
    """Retorna a instância compartilhada com o `asset_version` atualizado."""
    _templates.env.globals["asset_version"] = get_settings().asset_version
    return _templates
