"""Admin service — all business logic for admin operations.

Covers:
  - Rodadas: list, create, update
  - Jogos: list, create, update, launch result (recalculates Palpite.pontos)
  - Usuarios: list, create, reset_password, set_active
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Jogo, Palpite, Rodada, Usuario
from app.services.auth import hash_senha
from app.services.dashboard import STATUS_AGENDADO, STATUS_ENCERRADO
from app.services.prazo import rodada_aberta_para_edicao
from app.services.scoring import calcular_pontos
from app.services.tempo import agora as agora_dados


# ---------------------------------------------------------------------------
# View dataclasses
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class RodadaAdminView:
    id: int
    nome: str
    ordem: int
    aberta: bool
    abertura: datetime | None
    fechamento: datetime | None
    aberta_para_edicao: bool  # calculated via prazo
    qtd_jogos: int


@dataclass(slots=True)
class JogoAdminView:
    id: int
    rodada_id: int
    rodada_nome: str
    data_hora: datetime
    time_casa: str
    time_visitante: str
    gols_casa: int | None
    gols_visitante: int | None
    status: str


@dataclass(slots=True)
class UsuarioAdminView:
    id: int
    nome: str
    username: str
    is_admin: bool
    ativo: bool


# ---------------------------------------------------------------------------
# Rodadas
# ---------------------------------------------------------------------------


def listar_rodadas(db: Session) -> list[RodadaAdminView]:
    """Returns all rounds with calculated open-for-edit state and game count."""
    agora = agora_dados()

    stmt = select(
        Rodada.id,
        Rodada.nome,
        Rodada.ordem,
        Rodada.aberta,
        Rodada.abertura,
        Rodada.fechamento,
    ).order_by(Rodada.ordem)
    rows = db.execute(stmt).all()

    # Count games per round in a single query.
    stmt_count = select(Jogo.rodada_id, func.count(Jogo.id).label("qtd")).group_by(Jogo.rodada_id)
    count_rows = db.execute(stmt_count).all()
    count_map: dict[int, int] = {r.rodada_id: r.qtd for r in count_rows}

    result: list[RodadaAdminView] = []
    for r in rows:
        result.append(
            RodadaAdminView(
                id=r.id,
                nome=r.nome,
                ordem=r.ordem,
                aberta=r.aberta,
                abertura=r.abertura,
                fechamento=r.fechamento,
                aberta_para_edicao=rodada_aberta_para_edicao(
                    r.aberta, r.abertura, r.fechamento, agora
                ),
                qtd_jogos=count_map.get(r.id, 0),
            )
        )
    return result


def criar_rodada(db: Session, nome: str, ordem: int) -> Rodada:
    """Creates a new round.

    Raises ValueError for:
      - empty nome
      - duplicate ordem (IntegrityError from unique constraint)
    """
    nome = nome.strip()
    if not nome:
        raise ValueError("O nome da rodada não pode ser vazio.")

    rodada = Rodada(nome=nome, ordem=ordem)
    db.add(rodada)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise ValueError(f"Já existe uma rodada com a ordem {ordem}.")
    db.commit()
    db.refresh(rodada)
    return rodada


def atualizar_rodada(
    db: Session,
    rodada_id: int,
    aberta: bool,
    abertura: datetime | None,
    fechamento: datetime | None,
) -> Rodada:
    """Updates a round's open flag and time window.

    Raises ValueError if:
      - round not found
      - both abertura and fechamento are provided and abertura > fechamento
    """
    rodada = db.get(Rodada, rodada_id)
    if rodada is None:
        raise ValueError(f"Rodada {rodada_id} não encontrada.")

    if abertura is not None and fechamento is not None and abertura > fechamento:
        raise ValueError("A abertura não pode ser posterior ao fechamento.")

    rodada.aberta = aberta
    rodada.abertura = abertura
    rodada.fechamento = fechamento
    db.commit()
    db.refresh(rodada)
    return rodada


# ---------------------------------------------------------------------------
# Jogos
# ---------------------------------------------------------------------------


def listar_jogos(db: Session, rodada_id: int | None = None) -> list[JogoAdminView]:
    """Returns all games (optionally filtered by round)."""
    stmt = (
        select(
            Jogo.id,
            Jogo.rodada_id,
            Rodada.nome.label("rodada_nome"),
            Jogo.data_hora,
            Jogo.time_casa,
            Jogo.time_visitante,
            Jogo.gols_casa,
            Jogo.gols_visitante,
            Jogo.status,
        )
        .join(Rodada, Jogo.rodada_id == Rodada.id)
        .order_by(Rodada.ordem, Jogo.data_hora)
    )
    if rodada_id is not None:
        stmt = stmt.where(Jogo.rodada_id == rodada_id)

    rows = db.execute(stmt).all()
    return [
        JogoAdminView(
            id=r.id,
            rodada_id=r.rodada_id,
            rodada_nome=r.rodada_nome,
            data_hora=r.data_hora,
            time_casa=r.time_casa,
            time_visitante=r.time_visitante,
            gols_casa=r.gols_casa,
            gols_visitante=r.gols_visitante,
            status=r.status,
        )
        for r in rows
    ]


def criar_jogo(
    db: Session,
    rodada_id: int,
    data_hora: datetime,
    time_casa: str,
    time_visitante: str,
) -> Jogo:
    """Creates a new game.  Raises ValueError if the round does not exist."""
    rodada = db.get(Rodada, rodada_id)
    if rodada is None:
        raise ValueError(f"Rodada {rodada_id} não encontrada.")

    jogo = Jogo(
        rodada_id=rodada_id,
        data_hora=data_hora,
        time_casa=time_casa.strip(),
        time_visitante=time_visitante.strip(),
        status=STATUS_AGENDADO,
    )
    db.add(jogo)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise ValueError("Já existe um jogo com esses times nesta rodada.")
    db.commit()
    db.refresh(jogo)
    return jogo


def atualizar_jogo(
    db: Session,
    jogo_id: int,
    data_hora: datetime,
    time_casa: str,
    time_visitante: str,
) -> Jogo:
    """Updates a game's scheduling info.  Raises ValueError if not found."""
    jogo = db.get(Jogo, jogo_id)
    if jogo is None:
        raise ValueError(f"Jogo {jogo_id} não encontrado.")

    jogo.data_hora = data_hora
    jogo.time_casa = time_casa.strip()
    jogo.time_visitante = time_visitante.strip()
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise ValueError("Já existe um jogo com esses times nesta rodada.")
    db.commit()
    db.refresh(jogo)
    return jogo


def lancar_resultado(
    db: Session,
    jogo_id: int,
    gols_casa: int,
    gols_visitante: int,
) -> Jogo:
    """Records the final score, sets status to ENCERRADO, and recalculates all
    Palpite.pontos for the game in a single commit.

    Idempotent: re-running with a different score re-recalculates.
    Includes palpites of inactive users (D7 — consistent cache).
    Raises ValueError if game not found or gols < 0.
    """
    if gols_casa < 0 or gols_visitante < 0:
        raise ValueError("Os gols não podem ser negativos.")

    jogo = db.get(Jogo, jogo_id)
    if jogo is None:
        raise ValueError(f"Jogo {jogo_id} não encontrado.")

    jogo.gols_casa = gols_casa
    jogo.gols_visitante = gols_visitante
    jogo.status = STATUS_ENCERRADO

    # Recalculate ALL palpites (including inactive users — D7).
    stmt_palpites = select(Palpite).where(Palpite.jogo_id == jogo_id)
    palpites = db.scalars(stmt_palpites).all()
    for palpite in palpites:
        palpite.pontos = calcular_pontos(
            palpite_casa=palpite.gols_casa,
            palpite_visitante=palpite.gols_visitante,
            oficial_casa=gols_casa,
            oficial_visitante=gols_visitante,
        )

    db.commit()
    db.refresh(jogo)
    return jogo


# ---------------------------------------------------------------------------
# Usuarios
# ---------------------------------------------------------------------------


def listar_usuarios(db: Session) -> list[UsuarioAdminView]:
    """Returns all users (active and inactive)."""
    stmt = select(
        Usuario.id,
        Usuario.nome,
        Usuario.username,
        Usuario.is_admin,
        Usuario.ativo,
    ).order_by(Usuario.nome)
    rows = db.execute(stmt).all()
    return [
        UsuarioAdminView(
            id=r.id,
            nome=r.nome,
            username=r.username,
            is_admin=r.is_admin,
            ativo=r.ativo,
        )
        for r in rows
    ]


def criar_usuario(
    db: Session,
    nome: str,
    username: str,
    senha: str,
    is_admin: bool = False,
) -> Usuario:
    """Creates a user with a hashed password.

    Raises ValueError if username is already taken.
    """
    usuario = Usuario(
        nome=nome.strip(),
        username=username.strip(),
        senha_hash=hash_senha(senha),
        is_admin=is_admin,
        ativo=True,
    )
    db.add(usuario)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise ValueError(f"O username '{username}' já está em uso.")
    db.commit()
    db.refresh(usuario)
    return usuario


def resetar_senha(db: Session, usuario_id: int, nova_senha: str) -> Usuario:
    """Re-hashes and sets a new password.  Raises ValueError if not found."""
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise ValueError(f"Usuário {usuario_id} não encontrado.")

    usuario.senha_hash = hash_senha(nova_senha)
    db.commit()
    db.refresh(usuario)
    return usuario


def definir_ativo(db: Session, usuario_id: int, ativo: bool) -> Usuario:
    """Activates or deactivates a user.  Raises ValueError if not found."""
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise ValueError(f"Usuário {usuario_id} não encontrado.")

    usuario.ativo = ativo
    db.commit()
    db.refresh(usuario)
    return usuario
