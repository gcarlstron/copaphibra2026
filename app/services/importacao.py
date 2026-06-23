"""Service de importação de planilhas pela tela admin.

Camada fina entre o router e o importador (`scripts/importar_planilha.py`):
lista os `.xlsx` da pasta `import/` e dispara a importação de um deles, com
whitelist do nome (sem path traversal). O importador roda server-side, na
sessão do app (em produção, já com o `DATABASE_URL` certo) — sem precisar
mexer em variável de ambiente.
"""

from __future__ import annotations

from pathlib import Path

from app.config import PROJECT_ROOT
from scripts.importar_planilha import ResultadoImportacao, importar

PASTA_IMPORT: Path = PROJECT_ROOT / "import"


def listar_planilhas() -> list[str]:
    """Nomes dos arquivos .xlsx disponíveis na pasta import/ (ordenados)."""
    if not PASTA_IMPORT.exists():
        return []
    return sorted(p.name for p in PASTA_IMPORT.glob("*.xlsx"))


def importar_planilha(nome_arquivo: str) -> ResultadoImportacao:
    """Importa a planilha `nome_arquivo` (que deve estar em import/).

    Whitelist: só aceita um nome que está em `listar_planilhas()` — evita path
    traversal (ex.: `../../etc/...`). Levanta `ValueError` se o nome não existir
    na pasta. Repassa as demais exceções do importador (RuntimeError de
    aba/alinhamento, etc.) para o caller tratar.
    """
    if nome_arquivo not in listar_planilhas():
        raise ValueError(f"Planilha não encontrada na pasta import/: {nome_arquivo!r}")
    return importar(xlsx_path=PASTA_IMPORT / nome_arquivo)
