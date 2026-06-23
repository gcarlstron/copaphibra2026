"""Relatório READ-ONLY do estado do bolão — para análise antes de cada rodada.

Imprime no console (não escreve NADA no banco):
    - Classificação geral (idêntica à do dashboard: reusa `montar_dashboard`).
    - Tabela de cada grupo (reconstruída a partir dos confrontos) com os
      resultados já lançados + o confronto da próxima rodada de cada grupo.
    - Jogos sem resultado lançado (pendências que ainda não pontuaram).

Conexão: usa a `DATABASE_URL` do ambiente. Se não estiver setada, carrega o
`.env` da raiz do projeto (mesmo arquivo que o `uvicorn --env-file` usa), então
basta rodar:

    ./.venv/Scripts/python.exe scripts/relatorio.py

Para mirar outro banco, exporte `DATABASE_URL` antes (tem prioridade sobre o .env).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

_RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_RAIZ))


def _carregar_env(arquivo: Path) -> None:
    """Carrega `KEY=VALUE` do .env para o ambiente, sem sobrescrever o que já existe.

    Parser mínimo (sem dependência nova): ignora linhas vazias e comentários e
    divide no primeiro `=` (a URL do Postgres contém `=` nos query params).
    Precisa rodar ANTES de importar `app.*`, pois `app.config` lê o ambiente no
    import. Variáveis já presentes no ambiente têm prioridade (`setdefault`).
    """
    if not arquivo.exists():
        return
    for linha in arquivo.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        os.environ.setdefault(chave.strip(), valor.strip())


_carregar_env(_RAIZ / ".env")

# Evita mojibake (acentos) no console do Windows.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.database import SessionLocal, engine  # noqa: E402
from app.models.jogo import Jogo  # noqa: E402
from app.models.rodada import Rodada  # noqa: E402
from app.services.dashboard import montar_dashboard  # noqa: E402


@dataclass(slots=True)
class _LinhaTabela:
    time: str
    pontos: int = 0
    jogos: int = 0
    vitorias: int = 0
    empates: int = 0
    derrotas: int = 0
    gols_pro: int = 0
    gols_contra: int = 0

    @property
    def saldo(self) -> int:
        return self.gols_pro - self.gols_contra


def _imprimir_classificacao(db: Session) -> None:
    data = montar_dashboard(db)
    print("=" * 78)
    titulo = "CLASSIFICAÇÃO DO BOLÃO"
    if data.ultima_sync_texto:
        titulo += f"  (resultados atualizados {data.ultima_sync_texto})"
    print(titulo)
    print("=" * 78)
    print(f"{'#':>2} {'Jogador':<14} {'Pts':>4} {'9s':>3} {'6s':>3} {'4s':>3} {'3s':>3}")
    for item in data.classificacao:
        print(
            f"{item.posicao:>2} {item.nome:<14} {item.total:>4} "
            f"{item.qtd_9:>3} {item.qtd_6:>3} {item.qtd_4:>3} {item.qtd_3:>3}"
        )


def _reconstruir_grupos(jogos: list[Jogo]) -> list[set[str]]:
    """Agrupa os times por confronto (union-find) e devolve os grupos ordenados.

    Cada grupo da fase de grupos joga em turno único entre si, então os times de
    um mesmo grupo formam um componente conexo no grafo de confrontos.
    """
    pai: dict[str, str] = {}

    def find(x: str) -> str:
        pai.setdefault(x, x)
        while pai[x] != x:
            pai[x] = pai[pai[x]]
            x = pai[x]
        return x

    def union(a: str, b: str) -> None:
        pai[find(a)] = find(b)

    for jogo in jogos:
        union(jogo.time_casa, jogo.time_visitante)

    grupos: dict[str, set[str]] = {}
    for time in list(pai):
        grupos.setdefault(find(time), set()).add(time)
    return sorted(grupos.values(), key=lambda g: sorted(g)[0])


def _montar_tabela(grupo: set[str], jogos: list[Jogo]) -> list[_LinhaTabela]:
    """Calcula a tabela do grupo (3/1/0) com os jogos que já têm placar."""
    linhas = {time: _LinhaTabela(time=time) for time in grupo}
    for jogo in jogos:
        if jogo.time_casa not in grupo:
            continue
        if jogo.gols_casa is None or jogo.gols_visitante is None:
            continue
        for time, gp, gc in (
            (jogo.time_casa, jogo.gols_casa, jogo.gols_visitante),
            (jogo.time_visitante, jogo.gols_visitante, jogo.gols_casa),
        ):
            linha = linhas[time]
            linha.jogos += 1
            linha.gols_pro += gp
            linha.gols_contra += gc
            if gp > gc:
                linha.vitorias += 1
                linha.pontos += 3
            elif gp == gc:
                linha.empates += 1
                linha.pontos += 1
            else:
                linha.derrotas += 1
    return sorted(
        linhas.values(),
        key=lambda x: (x.pontos, x.saldo, x.gols_pro),
        reverse=True,
    )


def _imprimir_grupos(db: Session) -> None:
    jogos = list(
        db.execute(
            select(Jogo).order_by(Jogo.rodada_id, Jogo.data_hora, Jogo.id)
        ).scalars()
    )
    proxima = db.scalar(
        select(Rodada).where(Rodada.aberta == True).order_by(Rodada.ordem).limit(1)  # noqa: E712
    )

    print("\n" + "=" * 78)
    print("GRUPOS (inferidos pelos confrontos) — resultados lançados + próxima rodada")
    if proxima is not None:
        print(f"Próxima rodada aberta: {proxima.nome}")
    print("=" * 78)

    for indice, grupo in enumerate(_reconstruir_grupos(jogos)):
        rotulo = chr(ord("A") + indice)
        print(f"\nGrupo {rotulo}:")
        cab = f"   {'Time':<18} {'P':>2} {'J':>2} {'V':>2} {'E':>2} {'D':>2} {'GP':>3} {'GC':>3} {'SG':>3}"
        print(cab)
        for linha in _montar_tabela(grupo, jogos):
            print(
                f"   {linha.time:<18} {linha.pontos:>2} {linha.jogos:>2} "
                f"{linha.vitorias:>2} {linha.empates:>2} {linha.derrotas:>2} "
                f"{linha.gols_pro:>3} {linha.gols_contra:>3} {linha.saldo:>+3}"
            )
        if proxima is not None:
            for jogo in jogos:
                if jogo.rodada_id == proxima.id and jogo.time_casa in grupo:
                    print(f"     próx.: {jogo.time_casa}  x  {jogo.time_visitante}")


def _imprimir_pendencias(db: Session) -> None:
    """Jogos de rodadas FECHADAS sem placar (ainda valem 0 para todos)."""
    jogos = list(
        db.execute(
            select(Jogo)
            .join(Rodada, Jogo.rodada_id == Rodada.id)
            .where(Jogo.gols_casa.is_(None), Rodada.aberta == False)  # noqa: E712
            .order_by(Jogo.rodada_id, Jogo.data_hora)
        ).scalars()
    )
    if not jogos:
        return
    print("\n" + "=" * 78)
    print(f"ATENÇÃO: {len(jogos)} jogo(s) de rodada FECHADA sem resultado lançado")
    print("(esses palpites valem 0 para todos até o placar entrar)")
    print("=" * 78)
    for jogo in jogos:
        print(f"   rodada_id={jogo.rodada_id}  {jogo.time_casa} x {jogo.time_visitante}")


def main() -> None:
    print(f"[banco: {engine.dialect.name}]")
    db = SessionLocal()
    try:
        _imprimir_classificacao(db)
        _imprimir_grupos(db)
        _imprimir_pendencias(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
