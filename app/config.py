from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str = "Copa Phibra 2026"
    debug: bool = os.getenv("DEBUG", "0") == "1"
    secret_key: str = os.getenv("SECRET_KEY", "dev-secret-change-me")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./copa_phibra.db")

    session_https_only: bool = os.getenv("SESSION_HTTPS_ONLY", "0") == "1"

    espn_sync_intervalo_min: int = int(os.getenv("ESPN_SYNC_INTERVALO_MIN", "15"))
    # Intervalo curto usado quando há jogo ao vivo (ou recém-iniciado) — busca
    # quase em tempo real enquanto a bola rola.
    espn_sync_intervalo_ao_vivo_min: int = int(os.getenv("ESPN_SYNC_INTERVALO_AO_VIVO_MIN", "1"))
    espn_timeout_s: float = float(os.getenv("ESPN_TIMEOUT_S", "5"))
    # Orçamento total (segundos) para o sync síncrono no carregamento do dashboard.
    # Limita o tempo máximo que a página espera pela ESPN antes de renderizar com o
    # que já está no banco. Não afeta o caminho de background/cron (sem orçamento).
    # Default 15s: no Render free (instância fraca + latência à ESPN) 8s era curto
    # demais e o sync reivindicava o slot mas estourava antes de registrar. O cron
    # (/tarefas/sync) roda SEM deadline e é a garantia de completude.
    espn_sync_deadline_s: float = float(os.getenv("ESPN_SYNC_DEADLINE_S", "15"))
    # Janela à frente (dias) para ingestão de jogos do mata-mata via ESPN.
    # Default 30 cobre todo o mata-mata (R32 28/06 → Final 19/07 = 21 dias) a
    # partir de qualquer dia de execução.
    espn_lookahead_dias: int = int(os.getenv("ESPN_LOOKAHEAD_DIAS", "30"))

    # Intervalo (segundos) de auto-refresh da página quando há jogo ao vivo.
    auto_refresh_ao_vivo_s: int = int(os.getenv("AUTO_REFRESH_AO_VIVO_S", "60"))

    @property
    def templates_dir(self) -> Path:
        return PROJECT_ROOT / "app" / "templates"

    @property
    def static_dir(self) -> Path:
        return PROJECT_ROOT / "app" / "static"

    @property
    def asset_version(self) -> str:
        """Versão dos estáticos para cache-busting — muda a cada deploy.

        Produção (Render): usa o commit do deploy (`RENDER_GIT_COMMIT`), assim todo
        deploy invalida o cache do navegador. Local: cai no mtime de app.css/ui.js,
        mudando quando você edita os estáticos.
        """
        commit = os.getenv("RENDER_GIT_COMMIT", "").strip()
        if commit:
            return commit[:12]
        arquivos = [self.static_dir / "css" / "app.css", self.static_dir / "js" / "ui.js"]
        mtimes = [int(p.stat().st_mtime) for p in arquivos if p.exists()]
        return str(max(mtimes)) if mtimes else "dev"


def get_settings() -> Settings:
    return Settings()
