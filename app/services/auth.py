from __future__ import annotations

from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.models import Usuario

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Tamanho mínimo da nova senha ao trocar (mantido em sincronia com o `minlength`
# do formulário em templates/trocar_senha.html).
SENHA_MIN_LENGTH = 6


def hash_senha(senha: str) -> str:
    return pwd_context.hash(senha)


def verificar_senha(senha: str, senha_hash: str) -> bool:
    return pwd_context.verify(senha, senha_hash)


def alterar_senha(
    db: Session,
    usuario: Usuario,
    senha_atual: str,
    nova_senha: str,
    confirmacao: str,
) -> None:
    """Troca a senha do `usuario` após validar a senha atual e as regras da nova.

    Levanta ``ValueError`` (mensagem em pt-BR) se qualquer validação falhar;
    só persiste o novo hash quando tudo passa.
    """
    if not verificar_senha(senha_atual, usuario.senha_hash):
        raise ValueError("Senha atual incorreta.")

    if len(nova_senha) < SENHA_MIN_LENGTH:
        raise ValueError(f"A nova senha deve ter pelo menos {SENHA_MIN_LENGTH} caracteres.")

    if nova_senha != confirmacao:
        raise ValueError("A confirmação não corresponde à nova senha.")

    if verificar_senha(nova_senha, usuario.senha_hash):
        raise ValueError("A nova senha deve ser diferente da atual.")

    usuario.senha_hash = hash_senha(nova_senha)
    db.add(usuario)
    db.commit()
