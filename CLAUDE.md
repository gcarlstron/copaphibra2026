# CLAUDE.md — Copa Phibra 2026

Regras e convenções do projeto. **Estas instruções têm prioridade.** Para o desenho completo do sistema, ver [`ARQUITETURA.md`](ARQUITETURA.md).

## O que é

Bolão da Copa do Mundo 2026 (Copa Phibra). Cada Phibriano palpita os placares; o sistema
calcula os pontos pela LEGENDA e mantém a classificação com critérios de desempate.
Substitui as planilhas manuais usadas hoje. App web simples, de uso interno (~10 jogadores).

## Stack

- **Backend/UI:** FastAPI (Python 3.11+), server-rendered com **Jinja2 + HTMX + CSS**
- **Banco:** SQLite no início (arquivo local) → pronto para PostgreSQL
- **ORM/Migrations:** SQLAlchemy + Alembic
- **Auth:** sessão por cookie + senha com hash (lib `bcrypt`)
- App **único** — sem mobile, sem repo de frontend separado, sem Figma, sem serviços de nuvem

## Estrutura

```
app/
├── main.py            # cria o app FastAPI, monta rotas + templates
├── config.py          # SECRET, banco, buffer de prazo
├── database.py        # engine + sessão SQLAlchemy
├── models/            # Usuario, Rodada, Jogo, Palpite
├── schemas/           # Pydantic v2 (in/out)
├── routers/           # auth, dashboard, palpites, jogos, admin
├── services/          # LÓGICA DE NEGÓCIO — scoring.py, ranking.py, prazo.py
├── templates/         # Jinja2
└── static/            # css, htmx
migrations/            # Alembic
scripts/importar_planilha.py
tests/
```

## Regras invioláveis

1. **Lógica de negócio só em `app/services/`** — nunca em routers ou templates.
2. **Pontuação** segue a LEGENDA exatamente — `tests/test_scoring.py` (casos reais da planilha) tem que passar:
   - **9** = vencedor/empate com placar exato
   - **6** = vencedor + nº de gols do vencedor certo (placar não exato), ou empate com placar errado
   - **4** = vencedor + nº de gols do perdedor certo
   - **3** = só o vencedor
   - **0** = errou o vencedor / errou o empate
   - Desempate: mais jogos de 9 → 6 → 4 → 3 → sorteio.
3. **Prazo por Rodada** (controle manual do admin): rodada aberta = `aberta == True AND (sem janela OU abertura ≤ agora ≤ fechamento)`. **Revalidar sempre no backend** ao salvar palpite — nunca confiar só na tela.
4. **Privacidade:** palpites de outros jogadores só ficam visíveis **depois que a rodada fecha**.
5. **Autorização:** usuário edita só o próprio palpite; lançar resultado e gerenciar rodadas exige `is_admin`.
6. **Senha sempre com hash** (lib `bcrypt`, em `app/services/auth.py`) — nunca texto puro. Sem segredos no código (usar variáveis de ambiente).
7. **Alembic:** nunca editar uma migração já aplicada — sempre criar uma nova.

## Convenções de código

- PEP 8 + Black; `ruff` limpo. Type hints completos em toda função.
- Schemas Pydantic v2 para entrada/saída. Seleção explícita de colunas (sem `SELECT *`).
- Rotas protegidas usam `Depends(get_current_user)`; rotas de admin exigem `is_admin`.
- Templates: só apresentação. Estados loading/vazio/erro sempre tratados. UI simples e responsiva.

## Dados / domínio

- **10 jogadores ativos** (da planilha): Bernardo, Thiago, Ricardo, Fernando, Gustavo, Marcio, Gabriel, Renan, Soares, Marques. Os outros nomes da planilha não existem mais.
- **Rodadas da fase de grupos** (48 times, 24 jogos cada), mapeadas pelas linhas da aba `OFICIAL`: 1ª = 2–25, 2ª = 26–49, 3ª = 50–73, depois mata-mata.
- Dados iniciais entram via `scripts/importar_planilha.py` (jogos, resultados conhecidos, palpites existentes).

## Agentes

Definidos em `.claude/agents/`: **architect**, **backend**, **frontend** (UI), **project-manager**, **qa**.
Comece features não-triviais pelo **project-manager** (quebra em tarefas backend + UI).
**architect** e **qa** são on-demand — só quando solicitados.

## Workflow de commit

- Branch a partir de `main`: `feat/<escopo>`, `fix/<escopo>`, `chore/<escopo>`.
- Um commit por unidade lógica. Mensagem convencional (`feat`/`fix`/`chore`/`refactor`/`test`/`docs`).
- Atualizar `TASKS.md` (itens concluídos como `[x] ✅`) antes do commit.
- **Não fazer push** sem ser pedido.

## Rodar (a definir no scaffolding)

```bash
pip install -r requirements.txt
alembic upgrade head
python scripts/importar_planilha.py   # carga inicial da planilha
uvicorn app.main:app --reload
```
