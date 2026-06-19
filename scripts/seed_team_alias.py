"""Seed the team_alias table with FIFA/ESPN abbreviation ↔ PT-BR name mappings.

Idempotente: get-or-create por abreviação. Rodar 2× não duplica.

Estratégia de matching:
    - Lê os 48 nomes distintos de Jogo.time_casa/time_visitante do banco.
    - Para cada par (abreviacao, nome_candidato_pt, nome_en) do mapeamento estático,
      busca o nome exato do banco por comparação case-insensitive e sem acentos
      (usando unicodedata.normalize + casefold). Guarda a grafia EXATA do banco.
    - Aborta com lista dos não-casados se algum dos 48 ficar descoberto.

Fuso/timezone: Os times do banco foram importados da planilha; os nomes são
idênticos ao que está em Jogo.time_casa/time_visitante, que é a fonte da verdade.
"""

from __future__ import annotations

import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, text

from app.database import SessionLocal
from app.models.team_alias import TeamAlias

# ---------------------------------------------------------------------------
# Mapeamento estático: (nome_pt_candidato, abreviacao_espn, nome_en)
# O nome_pt_candidato é usado APENAS para o matching inicial (sem acentos/caixa).
# O nome gravado em `nome` virá sempre da grafia exata do banco.
# ---------------------------------------------------------------------------
_MAPEAMENTO_ESTATICO: list[tuple[str, str, str]] = [
    ("Alemanha", "GER", "Germany"),
    ("Argentina", "ARG", "Argentina"),
    ("Argelia", "ALG", "Algeria"),        # normalizado sem acento p/ matching
    ("Arabia Saudita", "KSA", "Saudi Arabia"),
    ("Australia", "AUS", "Australia"),
    ("Brasil", "BRA", "Brazil"),
    ("Belgica", "BEL", "Belgium"),
    ("Bosnia", "BIH", "Bosnia and Herzegovina"),
    ("Cabo Verde", "CPV", "Cape Verde"),
    ("Canada", "CAN", "Canada"),
    ("Catar", "QAT", "Qatar"),
    ("Colombia", "COL", "Colombia"),
    ("Coreia do Sul", "KOR", "South Korea"),
    ("Costa do Marfim", "CIV", "Ivory Coast"),
    ("Croacia", "CRO", "Croatia"),
    ("Curacao", "CUW", "Curacao"),
    ("Egito", "EGY", "Egypt"),
    ("Equador", "ECU", "Ecuador"),
    ("Escocia", "SCO", "Scotland"),
    ("Espanha", "ESP", "Spain"),
    ("Estados Unidos", "USA", "United States"),
    ("Franca", "FRA", "France"),
    ("Gana", "GHA", "Ghana"),
    ("Haiti", "HAI", "Haiti"),
    ("Holanda", "NED", "Netherlands"),
    ("Inglaterra", "ENG", "England"),
    ("Iraque", "IRQ", "Iraq"),
    ("Ira", "IRN", "Iran"),
    ("Japao", "JPN", "Japan"),
    ("Jordania", "JOR", "Jordan"),
    ("Marrocos", "MAR", "Morocco"),
    ("Mexico", "MEX", "Mexico"),
    ("Noruega", "NOR", "Norway"),
    ("Nova Zelandia", "NZL", "New Zealand"),
    ("Panama", "PAN", "Panama"),
    ("Paraguai", "PAR", "Paraguay"),
    ("Portugal", "POR", "Portugal"),
    ("RD Congo", "COD", "DR Congo"),
    ("Republica Tcheca", "CZE", "Czechia"),
    ("Senegal", "SEN", "Senegal"),
    ("Suecia", "SWE", "Sweden"),
    ("Suica", "SUI", "Switzerland"),
    ("Tunisia", "TUN", "Tunisia"),
    ("Turquia", "TUR", "Turkey"),
    ("Uruguai", "URU", "Uruguay"),
    ("Uzbequistao", "UZB", "Uzbekistan"),
    ("Africa do Sul", "RSA", "South Africa"),
    ("Austria", "AUT", "Austria"),
]


def _normalizar(s: str) -> str:
    """Remove acentos e passa para minúsculas para comparação fuzzy."""
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().casefold()


def main() -> None:
    db = SessionLocal()
    try:
        # 1. Lê todos os 48 nomes distintos do banco
        rows = db.execute(
            text(
                "SELECT DISTINCT time_casa FROM jogos "
                "UNION SELECT DISTINCT time_visitante FROM jogos"
            )
        ).fetchall()
        nomes_banco: list[str] = [r[0] for r in rows]
        nomes_banco_norm: dict[str, str] = {
            _normalizar(n): n for n in nomes_banco
        }

        # 2. Constrói lista final fazendo o match
        pares: list[tuple[str, str, str]] = []  # (nome_exato_banco, abrev, nome_en)
        nao_casados_estatico: list[str] = []

        for candidato, abrev, nome_en in _MAPEAMENTO_ESTATICO:
            chave = _normalizar(candidato)
            if chave in nomes_banco_norm:
                pares.append((nomes_banco_norm[chave], abrev, nome_en))
            else:
                nao_casados_estatico.append(candidato)

        if nao_casados_estatico:
            print(
                "ERRO: Os seguintes candidatos do mapeamento estático não "
                f"casaram com nenhum nome do banco:\n  {nao_casados_estatico}"
            )
            sys.exit(1)

        # 3. Verifica se TODOS os 48 do banco foram cobertos
        nomes_cobertos = {_normalizar(nome) for nome, _, _ in pares}
        nao_cobertos = [n for n in nomes_banco if _normalizar(n) not in nomes_cobertos]
        if nao_cobertos:
            print(
                "ERRO: Os seguintes nomes do banco NÃO foram cobertos pelo "
                f"mapeamento estático:\n  {nao_cobertos}"
            )
            sys.exit(1)

        # 4. Get-or-create (idempotente)
        criados = 0
        existentes = 0
        for nome_exato, abrev, nome_en in pares:
            existente = db.scalar(
                select(TeamAlias).where(TeamAlias.abreviacao == abrev)
            )
            if existente is None:
                db.add(TeamAlias(abreviacao=abrev, nome=nome_exato, nome_en=nome_en))
                criados += 1
            else:
                # Atualiza nome caso a grafia tenha mudado
                existente.nome = nome_exato
                existente.nome_en = nome_en
                existentes += 1

        db.commit()
        print(
            f"seed_team_alias concluído: {criados} criados, {existentes} já existiam. "
            f"Total: {criados + existentes} (esperado: 48)."
        )
        assert criados + existentes == 48, "Contagem inesperada!"

    finally:
        db.close()


if __name__ == "__main__":
    main()
