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
- Fase 9 concluída: revisão final de QA do sistema inteiro; 3 bloqueantes corrigidos (crash de timezone em `/palpites`, `SECRET_KEY` guard em produção, cookie de sessão endurecido) + importantes (gols negativos validados no backend, `bcrypt<5.0` pinado). Deploy preparado e **executado**: app no ar no Render + Neon, testado pelo operador.
- Fase 10 concluída (implementação): busca automática de resultados via ESPN, disparada no login (background, throttle persistido em `sync_state`, isolamento total de erro). De-para por abreviação FIFA (`team_alias`, 48 times). Reusa `admin.lancar_resultado`. Cliente `httpx2`. QA auditou o caminho do login (PRONTA).
- Fase 11 concluída: página `GET /jogos` (todos os jogos agrupados por rodada, com os pontos do PRÓPRIO usuário ao lado) + escudos dos times (ESPN) no detalhe e na lista (`team_alias.escudo_url`, derivado do padrão `.../countries/500/{abrev}.png`). Link "Jogos" no menu. Suíte em **177 testes**. Migrações (`7b24c90f7905`, `a1b2c3d4e5f6`) + seeds já aplicados na Neon.

## Estado atual (2026-06-19) — NO AR

- **Deploy feito:** Fases 10 + 11 pushadas (commits `0a084dd`, `b3cd79e`) → Render deployou. Migrações (`7b24c90f7905`, `a1b2c3d4e5f6`) + seeds (`team_alias` com escudos, `sync_state`) aplicados na Neon.
- **Sync de resultados funcionando em produção:** o disparo no login já preencheu na Neon os jogos de 17–18/06 com o placar correto da ESPN (Gana 1×0 Panamá, México 1×0 Coréia do Sul, Canadá 6×0 Catar, etc.). 28 jogos encerrados, 0 pendentes no passado — dados atualizados. Líder atual: Marcio (79 pts).
- Suíte: **177 testes**. Repo: `gcarlstron/copaphibra2026` (branch `main`).

## Próxima Etapa / follow-ups em aberto

- **Conta `admin` aparece na classificação** (com 0 pts) — `montar_dashboard` inclui todos os usuários ativos. Decidir: excluir contas `is_admin` do ranking (provável) — ajuste pequeno em `services/dashboard.py`.
- **Segurança (pendente desde o deploy inicial):** trocar a senha do `admin` (`admin123`) via Admin → Usuários; rotacionar a senha do banco na Neon (foi compartilhada em texto na conversa) e atualizar `DATABASE_URL` no Render.
- (Opcional) escudos pequenos nas listas do dashboard (exigiria expor `escudo_url` em `JogoResumoView`).
- **Nota:** há edição de `HANDOFF.md` (e possivelmente `TASKS.md`) não commitada ao fim desta sessão — commitar/pushar na retomada.
- Pós-deploy ainda pendente: trocar senha do `admin` (`admin123`); rotacionar a senha do banco na Neon (foi compartilhada em texto).
- Possível próximo: indicador "última atualização" no dashboard (Fase 10g, opcional); limpar follow-ups técnicos abaixo.

### Arquitetura da Fase 10 (para quem continuar)
- `services/espn.py` (cliente + parser puro, resolve home/away por `homeAway`), `services/sync_resultados.py` (`sincronizar_resultados` + `disparar_sync_se_necessario`), `models/team_alias.py` + `models/sync_state.py`, `scripts/seed_team_alias.py`, hook em `routers/auth.py` (`BackgroundTasks`).
- ESPN: `https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates=AAAAMMDD` (campos: `competitors[].team.abbreviation`, `.score`, `.homeAway`, `status.type.name`=`STATUS_FULL_TIME`).
- Credenciais: admin = `admin`/`admin123`; jogadores = primeiro nome minúsculo / `copaphibra2026`.

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
- Testes: `tests/conftest.py` define `SECRET_KEY` para a suíte não esbarrar no guard de produção. Suíte atual: **109 testes**.
- **Migrações portáveis (SQLite ↔ Postgres):** defaults booleanos em migração devem usar `sa.false()`/`sa.true()` — NUNCA `sa.text("0")`/`sa.text("1")` (o `0`/`1` quebra no Postgres: "column is boolean but default is integer"). A migração inicial foi corrigida por isso ao subir na Neon. `DATABASE_URL` é normalizado para `postgresql+psycopg://` no app e no `migrations/env.py`.

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