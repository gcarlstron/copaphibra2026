# Handoff - Copa Phibra 2026

Este documento resume o estado atual do projeto para retomada por outra IA ou por um novo turno.

## Status

- Fase 1 concluída: scaffolding, `requirements.txt`, `README.md`, `app/config.py`, `app/database.py`, `app/main.py`, Alembic e UI base.
- Fase 2 concluída: models `Usuario`, `Rodada`, `Jogo`, `Palpite` e migração inicial aplicada.
- Fase 3 concluída: `services/scoring.py`, `services/prazo.py`, `services/ranking.py` e testes de regra.
- Fase 4 concluída: autenticação por sessão/cookie, hash de senha, login/logout e tela de login.
- Fase 5 concluída: fluxo de palpites com `GET /palpites` e `POST /palpites/{jogo_id}`.
- Fase 6 concluída: dashboard/classificação (`GET /` em router dedicado) e detalhe do jogo (`GET /jogos/{id}`), com UI definitiva.
- Fase 7 concluída: Admin completo — `services/admin.py` + `routers/admin.py` + telas `admin/` (rodadas, jogos, usuários). Lançamento de resultado recalcula `Palpite.pontos` de todos os palpites do jogo.
- Fase 8 concluída: `scripts/importar_planilha.py` carregou a fase de grupos (10 jogadores, 3 rodadas, 72 jogos, 480 palpites) a partir de `import/COPA PHIBRA 2026 OFICIAL ATÉ A FINAL SEGUNDA FASE.xlsx`. QA aprovou: os 10 totais por jogador batem com a planilha.
- Fase 9 (fechamento) quase concluída: revisão final de QA do sistema inteiro feita; 3 bloqueantes corrigidos (crash de timezone em `/palpites`, `SECRET_KEY` guard em produção, cookie de sessão endurecido) + importantes (gols negativos validados no backend, `bcrypt<5.0` pinado). Deploy preparado (`DEPLOY.md`, `.env.example`, README). Suíte em **101 testes, tudo passando**. Falta só a ação de deploy no servidor (operador).

## Próxima Etapa

- **Deploy escolhido: Render (web service free) + Neon (Postgres free).** App já pronto para Postgres (`psycopg`, normalização de `DATABASE_URL`, `render.yaml`). Seguir `DEPLOY.md` Opção A: criar banco na Neon → subir repo privado no GitHub → Blueprint no Render → definir `DATABASE_URL`/`SECRET_KEY`/`DEBUG=0`/`SESSION_HTTPS_ONLY=1` → carga inicial (`criar_admin` + `importar_planilha`) contra a Neon → trocar senha do admin.
- Opcional: limpar os follow-ups técnicos abaixo antes de considerar o projeto 100% fechado.

## Pendências e follow-ups (não bloqueantes)

- Fase 2: `app/schemas/` ainda vazio; entrada hoje via `Form(...)` + dataclasses de view. Formalizar Pydantic v2 quando uma rota precisar de payload JSON.
- Fase 7: erros de validação em `/admin/jogos` retornam HTTP 400 (página padrão) em vez de re-render com banner amigável como rodadas/usuários.
- Fase 8 (QA): (1) re-rodar o importador reseta a senha de usuários já existentes — não resetar `senha_hash` de quem já existe; (2) faltam testes de idempotência (rodar 2x) e de não-clobber do admin; (3) `Jogo` sem `UniqueConstraint(rodada_id, time_casa, time_visitante)` — idempotência de jogo só por query, considerar nova migração; (4) type hints fracos (`object`) em `importar_planilha.py`.

## Estado de dados (após import)

- Banco `copa_phibra.db` populado: 10 jogadores (não-admin) + usuário `admin/admin123` (gestão); senha temporária dos jogadores definida na importação.
- 3 rodadas de grupos, todas `aberta=False`. 1ª rodada com 22 jogos já com resultado; 2ª/3ª sem resultado. 3ª rodada ainda sem palpites na planilha.
- Para recarregar: `python scripts/importar_planilha.py` (idempotente — mas hoje reseta senhas, ver follow-up).

## Arquitetura Já Implantada

- FastAPI server-rendered com Jinja2 + HTMX + CSS.
- SQLite como banco local inicial, com Alembic já configurado e migração aplicada.
- Sessão por cookie com `SessionMiddleware`.
- Lógica de negócio concentrada em `app/services/`.

## Padrões Importantes

- `app/services/prazo.py` normaliza datas para UTC porque o SQLite pode devolver datetime sem timezone. **Sempre** comparar datas via as funções de `prazo.py` (`rodada_aberta_para_edicao`, `palpites_de_terceiros_visiveis`) — comparar `agora` (aware) com colunas do banco (naive) direto causa `TypeError`/500 (foi o bug corrigido na Fase 9 em `palpites.py`).
- `app/services/auth.py` usa `passlib[bcrypt]`.
- Na stack atual, `bcrypt<5.0` é necessário no ambiente para evitar falha do backend de hash (pinado no `requirements.txt`).
- `Jinja2Templates.TemplateResponse` requer `request` como primeiro argumento nesta versão do FastAPI/Starlette.
- O smoke test depende de `httpx2` no ambiente de testes.
- **Produção:** `create_app()` recusa subir se `DEBUG=0` e `SECRET_KEY` for o padrão/vazio. Cookie de sessão com `SameSite=lax` + `Secure` controlado por `SESSION_HTTPS_ONLY`. Env vars: `SECRET_KEY`, `DEBUG`, `DATABASE_URL`, `SESSION_HTTPS_ONLY` (ver `DEPLOY.md` / `.env.example`).
- Testes: `tests/conftest.py` define `SECRET_KEY` para a suíte não esbarrar no guard de produção. Suíte atual: **101 testes**.

## Comandos de Trabalho

```bash
C:/Users/PHIBRA/source/repos/CopaPhibra/.venv/Scripts/python.exe -m pytest tests/test_smoke.py
C:/Users/PHIBRA/source/repos/CopaPhibra/.venv/Scripts/python.exe -m pytest tests/test_auth.py tests/test_palpites.py tests/test_scoring.py tests/test_prazo.py tests/test_ranking.py
C:/Users/PHIBRA/source/repos/CopaPhibra/.venv/Scripts/python.exe -m alembic upgrade head
```

## Arquivos-Chave

- [app/main.py](app/main.py)
- [app/routers/auth.py](app/routers/auth.py)
- [app/routers/palpites.py](app/routers/palpites.py)
- [app/services/scoring.py](app/services/scoring.py)
- [app/services/prazo.py](app/services/prazo.py)
- [app/services/ranking.py](app/services/ranking.py)
- [app/services/palpites.py](app/services/palpites.py)
- [app/services/dashboard.py](app/services/dashboard.py)
- [app/services/jogos.py](app/services/jogos.py)
- [app/routers/dashboard.py](app/routers/dashboard.py)
- [app/routers/jogos.py](app/routers/jogos.py)
- [app/services/admin.py](app/services/admin.py)
- [app/routers/admin.py](app/routers/admin.py)
- [TASKS.md](TASKS.md)

## Observação

`TASKS.md` reflete o que foi concluído (Fases 0–8). A fase seguinte em aberto é a Fase 9 (Fechamento: revisão final de QA + deploy interno).

Notas da Fase 6 para quem continuar:
- `Jogo.status` é `String(20)` sem enum; os valores usados são `"agendado"` (default) e `"encerrado"`, expostos como constantes `STATUS_AGENDADO`/`STATUS_ENCERRADO` em `app/services/dashboard.py` — reuse-as.
- O dashboard agrega os palpites do banco para montar a classificação (a lacuna que faltava em `ranking.py`, que só tinha os helpers de regra).
- Privacidade do detalhe do jogo é decidida por `prazo.palpites_de_terceiros_visiveis(...)`; não reimplemente.

Notas da Fase 7 (Admin) para quem continuar:
- Autorização das rotas de admin (D6): anônimo é redirecionado para `/login`; usuário logado não-admin recebe 403. Tratado no próprio `routers/admin.py` (não alterou `get_current_admin`).
- Lançar resultado (`services/admin.py::lancar_resultado`) é a peça central: grava gols, marca o jogo como `encerrado` e recalcula `Palpite.pontos` de TODOS os palpites do jogo (inclusive de inativos) via `scoring.calcular_pontos(palpite_casa, palpite_visitante, oficial_casa, oficial_visitante)`, num único commit. É idempotente.
- Funções reusáveis confirmadas: `auth.hash_senha(senha)` / `auth.verificar_senha(senha, senha_hash)`; coluna de hash = `Usuario.senha_hash`.