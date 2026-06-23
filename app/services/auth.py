from __future__ import annotations

import bcrypt
from sqlalchemy.orm import Session

from app.models import Usuario

# Tamanho mínimo da nova senha ao trocar (mantido em sincronia com o `minlength`
# do formulário em templates/trocar_senha.html).
SENHA_MIN_LENGTH = 6

# Limite do bcrypt: senhas com mais de 72 bytes são rejeitadas pela lib (em vez
# de truncadas silenciosamente). Validamos antes para dar um erro amigável.
SENHA_MAX_BYTES = 72


def hash_senha(senha: str) -> str:
    """Gera o hash bcrypt da senha (formato ``$2b$``, compatível com hashes legados).

    Usa a lib ``bcrypt`` diretamente — o ``passlib`` foi removido por ser incompatível
    com Python 3.13+ e disparar avisos com bcrypt >= 4.1.

    Levanta ``ValueError`` se a senha exceder ``SENHA_MAX_BYTES`` bytes (limite do bcrypt).
    """
    if len(senha.encode("utf-8")) > SENHA_MAX_BYTES:
        raise ValueError(f"A senha não pode ter mais de {SENHA_MAX_BYTES} bytes.")
    return bcrypt.hashpw(senha.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verificar_senha(senha: str, senha_hash: str) -> bool:
    """Verifica a senha contra o hash bcrypt armazenado.

    Retorna ``False`` (em vez de propagar) quando o hash está malformado/vazio
    (ex.: dado legado ou corrompido) ou a senha excede o limite do bcrypt — nesses
    casos a lib levanta ``ValueError``. Assim um login com hash inválido vira 401,
    não 500.
    """
    try:
        return bcrypt.checkpw(senha.encode("utf-8"), senha_hash.encode("utf-8"))
    except ValueError:
        return False


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

    if len(nova_senha.encode("utf-8")) > SENHA_MAX_BYTES:
        raise ValueError(f"A nova senha não pode ter mais de {SENHA_MAX_BYTES} bytes.")

    if nova_senha != confirmacao:
        raise ValueError("A confirmação não corresponde à nova senha.")

    if verificar_senha(nova_senha, usuario.senha_hash):
        raise ValueError("A nova senha deve ser diferente da atual.")

    usuario.senha_hash = hash_senha(nova_senha)
    db.add(usuario)
    db.commit()
