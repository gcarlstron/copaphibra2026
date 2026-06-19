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
    espn_timeout_s: float = float(os.getenv("ESPN_TIMEOUT_S", "5"))

    @property
    def templates_dir(self) -> Path:
        return PROJECT_ROOT / "app" / "templates"

    @property
    def static_dir(self) -> Path:
        return PROJECT_ROOT / "app" / "static"


def get_settings() -> Settings:
    return Settings()
