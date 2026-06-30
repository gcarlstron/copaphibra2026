"""Previsão dos jogos do mata-mata via IA (Gemini), a partir dos dados do bolão.

Lê do banco (o mesmo que o app usa — respeita ``DATABASE_URL``, então funciona
com SQLite local ou Neon/Postgres) e, para cada jogo do mata-mata ainda sem
resultado, pede ao Gemini uma previsão de placar levando em conta:

  - a CLASSIFICAÇÃO atual dos jogadores ativos (quem pontua mais tem mais
    "peso" — a pontuação é a soma de ``palpites.pontos`` pela LEGENDA, com os
    mesmos critérios de desempate da tela de classificação);
  - o HISTÓRICO de palpites do grupo (tendência/consenso).

Este é um script de ANÁLISE externa — não é lógica do app. Não grava nada no
banco; apenas lê e imprime as previsões.

Uso:
    # a chave da API fica em variável de ambiente (nunca no código)
    export GEMINI_API_KEY=...        # Linux/macOS
    $env:GEMINI_API_KEY = "..."      # PowerShell
    python scripts/previsao_mata_mata.py

Requisitos (não fazem parte do app — instale só para rodar este script):
    pip install google-genai
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap de sys.path para permitir ``import app...`` ao rodar diretamente.
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

# Console do Windows usa cp1252 por padrão e quebra com emoji/acentos (inclusive
# na resposta da IA). Força UTF-8 na saída quando o terminal permitir.
for _fluxo in (sys.stdout, sys.stderr):
    try:
        _fluxo.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass


def _carregar_env(caminho: Path) -> None:
    """Carrega variáveis de um .env para o ambiente (sem dependências externas).

    Precisa rodar ANTES de importar ``app.database``, que lê ``DATABASE_URL`` no
    momento do import. Usa ``setdefault`` para que uma variável já definida no
    ambiente real (ex.: produção/Render) tenha prioridade sobre o arquivo.
    """
    if not caminho.exists():
        return
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, _, valor = linha.partition("=")
        os.environ.setdefault(chave.strip(), valor.strip().strip('"').strip("'"))


# Carrega o .env da raiz do projeto antes de qualquer import que leia env vars.
_carregar_env(_PROJECT_ROOT / ".env")

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models import Jogo, Palpite, Rodada, Usuario  # noqa: E402
from app.services.ranking import chave_de_ranking, contar_buckets_de_pontos  # noqa: E402

# As ordens 1–3 são a fase de grupos; ordem >= 4 é mata-mata (ver
# app/services/espn.py::FASES_MATA_MATA). Jogo pendente = ainda "agendado".
ORDEM_PRIMEIRO_MATA_MATA = 4
STATUS_AGENDADO = "agendado"

MODELO_GEMINI = "gemini-2.5-flash"


@dataclass(slots=True)
class ItemRanking:
    nome: str
    total: int
    qtd_9: int
    qtd_6: int
    qtd_4: int
    qtd_3: int


@dataclass(slots=True)
class JogoPendente:
    fase: str
    time_casa: str
    time_visitante: str
    data_hora: datetime | None


@dataclass(slots=True)
class PalpiteHistorico:
    usuario: str
    fase: str
    time_casa: str
    time_visitante: str
    palpite_gols_casa: int
    palpite_gols_visitante: int


def montar_classificacao(db: Session) -> list[ItemRanking]:
    """Classificação dos jogadores ativos pela LEGENDA (total + buckets, com desempate).

    Espelha a lógica de ``app/services/dashboard.py::_montar_classificacao``: a
    pontuação é a soma dos ``palpites.pontos`` (não há coluna acumulada), e o
    desempate segue 9 → 6 → 4 → 3. Reusa as funções do serviço de ranking.
    """
    stmt = (
        select(Usuario.id, Usuario.nome, Palpite.pontos)
        .outerjoin(Palpite, Palpite.usuario_id == Usuario.id)
        .where(Usuario.ativo == True)  # noqa: E712
    )

    pontos_por_usuario: dict[int, list[int]] = {}
    nome_por_usuario: dict[int, str] = {}
    for row in db.execute(stmt).all():
        nome_por_usuario[row.id] = row.nome
        lista = pontos_por_usuario.setdefault(row.id, [])
        if row.pontos is not None:  # outer join: usuário sem palpites vem com NULL
            lista.append(row.pontos)

    itens: list[ItemRanking] = []
    for usuario_id, pontos in pontos_por_usuario.items():
        buckets = contar_buckets_de_pontos(pontos)
        itens.append(
            ItemRanking(
                nome=nome_por_usuario[usuario_id],
                total=sum(pontos),
                qtd_9=buckets[9],
                qtd_6=buckets[6],
                qtd_4=buckets[4],
                qtd_3=buckets[3],
            )
        )

    itens.sort(
        key=lambda e: chave_de_ranking(e.total, e.qtd_9, e.qtd_6, e.qtd_4, e.qtd_3),
        reverse=True,
    )
    return itens


def buscar_jogos_pendentes(db: Session) -> list[JogoPendente]:
    """Jogos do mata-mata ainda sem resultado (status 'agendado'), do mais cedo p/ o mais tarde."""
    stmt = (
        select(
            Rodada.nome.label("fase"),
            Jogo.time_casa,
            Jogo.time_visitante,
            Jogo.data_hora,
        )
        .join(Rodada, Jogo.rodada_id == Rodada.id)
        .where(Rodada.ordem >= ORDEM_PRIMEIRO_MATA_MATA)
        .where(Jogo.status == STATUS_AGENDADO)
        .order_by(Jogo.data_hora.asc())
    )
    return [
        JogoPendente(
            fase=row.fase,
            time_casa=row.time_casa,
            time_visitante=row.time_visitante,
            data_hora=row.data_hora,
        )
        for row in db.execute(stmt).all()
    ]


def buscar_historico_palpites(db: Session) -> list[PalpiteHistorico]:
    """Todos os palpites do grupo, com nomes de time e a fase, p/ a IA captar tendências."""
    stmt = (
        select(
            Usuario.nome.label("usuario"),
            Rodada.nome.label("fase"),
            Jogo.time_casa,
            Jogo.time_visitante,
            Palpite.gols_casa,
            Palpite.gols_visitante,
        )
        .join(Usuario, Palpite.usuario_id == Usuario.id)
        .join(Jogo, Palpite.jogo_id == Jogo.id)
        .join(Rodada, Jogo.rodada_id == Rodada.id)
        .where(Usuario.ativo == True)  # noqa: E712
        .order_by(Rodada.ordem.asc(), Jogo.data_hora.asc())
    )
    return [
        PalpiteHistorico(
            usuario=row.usuario,
            fase=row.fase,
            time_casa=row.time_casa,
            time_visitante=row.time_visitante,
            palpite_gols_casa=row.gols_casa,
            palpite_gols_visitante=row.gols_visitante,
        )
        for row in db.execute(stmt).all()
    ]


def _to_json(itens: list) -> str:
    """Serializa dataclasses (incluindo datetime) em JSON legível p/ o prompt."""

    def default(obj: object) -> object:
        if isinstance(obj, datetime):
            return obj.isoformat()
        if hasattr(obj, "__dict__") or hasattr(obj, "__slots__"):
            return {s: getattr(obj, s) for s in obj.__slots__}  # type: ignore[attr-defined]
        raise TypeError(f"Não serializável: {type(obj)!r}")

    return json.dumps(itens, default=default, ensure_ascii=False, indent=2)


def montar_prompt(
    jogo: JogoPendente,
    contexto_ranking: str,
    contexto_palpites: str,
) -> str:
    quando = jogo.data_hora.isoformat() if jogo.data_hora else "a definir"
    return f"""
Você é um analista de dados especialista em futebol e inteligência preditiva para bolões da Copa do Mundo.
Acabou a fase de grupos e estamos no mata-mata.

Classificação atual dos jogadores ativos (quem tem mais pontos — e mais acertos
exatos, os "qtd_9" — tem maior precisão histórica; dê mais peso à opinião deles):
{contexto_ranking}

Histórico de palpites do grupo até agora:
{contexto_palpites}

Gere uma previsão para o seguinte jogo:
- Fase: {jogo.fase}
- Confronto: {jogo.time_casa} x {jogo.time_visitante}
- Data/hora: {quando}

Instruções de análise:
1. Calcule a tendência de consenso do grupo para este confronto.
2. Dê peso maior à opinião dos jogadores no topo da classificação.
3. Como é mata-mata, sugira o placar mais provável no tempo normal (90 min) e
   indique quem tem mais chance de avançar (prorrogação/pênaltis).
4. Explique brevemente o padrão que você detectou nos dados para justificar.

Responda de forma limpa e direta, em português.
""".strip()


def main() -> int:
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print(
            "❌ Defina a variável de ambiente GEMINI_API_KEY antes de rodar.\n"
            '   PowerShell: $env:GEMINI_API_KEY = "sua-chave"',
            file=sys.stderr,
        )
        return 1

    try:
        from google import genai  # import tardio: dependência só deste script
        from google.genai import errors as genai_errors
    except ModuleNotFoundError:
        print(
            "❌ Pacote 'google-genai' não instalado. Rode: pip install google-genai",
            file=sys.stderr,
        )
        return 1

    print("📊 Coletando dados do banco...")
    db = SessionLocal()
    try:
        ranking = montar_classificacao(db)
        historico = buscar_historico_palpites(db)
        pendentes = buscar_jogos_pendentes(db)
    finally:
        db.close()

    contexto_ranking = _to_json(ranking)
    contexto_palpites = _to_json(historico)

    print(f"⚽ {len(pendentes)} jogo(s) pendente(s) do mata-mata encontrado(s).")
    if not pendentes:
        print("Nada a prever — nenhum jogo de mata-mata com status 'agendado'.")
        return 0

    client = genai.Client(api_key=api_key)

    for jogo in pendentes:
        print(f"\n🔮 Analisando: {jogo.time_casa} x {jogo.time_visitante} ({jogo.fase})...")
        prompt = montar_prompt(jogo, contexto_ranking, contexto_palpites)
        try:
            response = client.models.generate_content(model=MODELO_GEMINI, contents=prompt)
        except genai_errors.ClientError as exc:
            # 429 = cota/créditos esgotados: não adianta insistir nos demais jogos.
            if exc.code == 429:
                print(
                    "\n❌ Gemini sem cota/créditos (429 RESOURCE_EXHAUSTED). "
                    "Verifique o billing em https://ai.studio/projects e tente de novo.",
                    file=sys.stderr,
                )
                return 1
            print(f"⚠️  Falha neste jogo ({exc.code}): {exc.message}", file=sys.stderr)
            continue
        print("-" * 50)
        print(response.text)
        print("-" * 50)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
