"""Cria (ou atualiza) um usuário admin para testes manuais.

Uso:
    python scripts/criar_admin.py                      # admin/admin123 (padrão)
    python scripts/criar_admin.py joao senha123 "João" # username, senha, nome

Reusa o hash de senha de app.services.auth — nunca grava senha em texto puro.
Idempotente: se o username já existe, atualiza a senha e garante is_admin/ativo.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.database import SessionLocal
from app.models.usuario import Usuario
from app.services.auth import hash_senha


def main() -> None:
    username = sys.argv[1] if len(sys.argv) > 1 else "admin"
    senha = sys.argv[2] if len(sys.argv) > 2 else "admin123"
    nome = sys.argv[3] if len(sys.argv) > 3 else "Administrador"

    db = SessionLocal()
    try:
        usuario = db.execute(
            select(Usuario).where(Usuario.username == username)
        ).scalar_one_or_none()

        if usuario is None:
            usuario = Usuario(
                nome=nome,
                username=username,
                senha_hash=hash_senha(senha),
                is_admin=True,
                ativo=True,
            )
            db.add(usuario)
            acao = "criado"
        else:
            usuario.senha_hash = hash_senha(senha)
            usuario.is_admin = True
            usuario.ativo = True
            acao = "atualizado"

        db.commit()
        print(f"Usuário admin {acao}: username={username!r} senha={senha!r}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
