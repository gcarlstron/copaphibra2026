# TASKS — Copa Phibra 2026

Convenção: `- [ ]` pendente · `- [~]` em andamento (com data) · `- [x] ✅` concluído.
Nunca apagar itens concluídos — o histórico importa.

Para retomada rápida em outra IA, ler [HANDOFF.md](HANDOFF.md) primeiro.

---

## Fase 0 — Definição (concluída)

- [x] ✅ Analisar a planilha e extrair regras (pontuação, desempate, prazo) — 2026-06-18
- [x] ✅ Escrever `ARQUITETURA.md` — 2026-06-18
- [x] ✅ Definir stack: FastAPI + Jinja2/HTMX + SQLite, login por usuário/senha, cada um digita o próprio palpite — 2026-06-18
- [x] ✅ Ajustar agentes `.claude/` para o projeto (sem Figma) — 2026-06-18
- [x] ✅ Criar `CLAUDE.md` e `TASKS.md` — 2026-06-18

---

## Fase 1 — Scaffolding

- [x] ✅ Estrutura do projeto (`app/`, `migrations/`, `tests/`) — 2026-06-18 _(obs.: `scripts/` ainda não criado; vem na Fase 8)_
- [x] ✅ `requirements.txt` (fastapi, uvicorn, sqlalchemy, alembic, pydantic, passlib[bcrypt], jinja2, python-multipart, openpyxl, pytest) — 2026-06-18
- [x] ✅ `app/config.py`, `app/database.py`, `app/main.py` (app FastAPI + montagem de templates/estáticos) — 2026-06-18
- [x] ✅ Configurar Alembic — 2026-06-18
- [x] ✅ `README.md` com passos para rodar — 2026-06-18
- [x] ✅ Esqueleto de `base.html` + `static/css/app.css` — 2026-06-18

## Fase 2 — Modelo de dados e migrações

- [x] ✅ Models: `Usuario`, `Rodada`, `Jogo`, `Palpite` → @backend — 2026-06-18
- [ ] Schemas Pydantic (in/out) → @backend _(parcial: entrada via `Form(...)` nos routers e dataclasses de view em `services/palpites.py`; pacote `app/schemas/` ainda vazio — formalizar schemas Pydantic v2 quando uma rota precisar de payload JSON estruturado)_
- [x] ✅ Migração inicial (`alembic revision --autogenerate`) — `migrations/versions/0439d0e80604_initial_schema.py` → @backend — 2026-06-18

## Fase 3 — Lógica de negócio (services) + testes

- [x] ✅ `services/scoring.py` — cálculo de pontos pela LEGENDA → @backend — 2026-06-18
- [x] ✅ `tests/test_scoring.py` — casos (9/6/4/3/0) validados contra a planilha → @backend — 2026-06-18
- [x] ✅ `services/prazo.py` — rodada aberta = `aberta AND janela`; visibilidade de palpites alheios → @backend — 2026-06-18
- [x] ✅ `services/ranking.py` — helpers de desempate (`contar_buckets_de_pontos`, `chave_de_ranking` 9→6→4→3) → @backend — 2026-06-18 _(obs.: agregação dos palpites do banco para montar a classificação será feita na Fase 6, no service do dashboard)_
- [x] ✅ `tests/test_prazo.py` e `tests/test_ranking.py` → @backend — 2026-06-18

## Fase 4 — Autenticação

- [x] ✅ Hash de senha (passlib) + verificação no login → @backend — 2026-06-18
- [x] ✅ Sessão por cookie; `get_current_user` e `get_current_admin` → @backend — 2026-06-18
- [x] ✅ Rota `POST /login`, `POST /logout` + tela `login.html` → @backend + @frontend — 2026-06-18

## Fase 5 — Palpites (fluxo principal do jogador)

- [x] ✅ `GET /palpites` — meus palpites agrupados por rodada → @backend — 2026-06-18
- [x] ✅ `POST /palpites/{jogo_id}` — salvar/editar (revalida rodada aberta) → @backend — 2026-06-18
- [x] ✅ Tela `palpites.html` por rodada + salvar via HTMX → @frontend — 2026-06-18

## Fase 6 — Dashboard e detalhe do jogo (concluída — 2026-06-18)

Contrato e detalhamento abaixo. Ordem de execução: backend (dono do contrato) → frontend.

### 6a — Dashboard / classificação (`GET /`)
- [x] ✅ `services/dashboard.py` — `montar_dashboard(db, agora)`: agrega palpites na classificação (posição, nome, total, qtd_9/6/4/3) reusando `ranking.contar_buckets_de_pontos` + `ranking.chave_de_ranking`; monta jogos recentes/próximos e rodadas abertas; constantes `STATUS_ENCERRADO`/`STATUS_AGENDADO`; seleção explícita de colunas → @backend — 2026-06-18
- [x] ✅ Mover `GET /` de `app/main.py` para `app/routers/dashboard.py` (router dedicado, `Depends(get_current_user)`) e registrar em `main.py` → @backend — 2026-06-18
- [x] ✅ `tests/test_dashboard.py` — ordenação por pontos + desempate; usuário inativo fora do ranking; jogos recentes/próximos; rodadas abertas; auth (17 testes) → @backend — 2026-06-18
- [x] ✅ Tela `dashboard.html` (substitui o placeholder): tabela de classificação (com destaque do próprio usuário), blocos de resultados/próximos jogos, banner de rodadas abertas com prazo; estados vazio/erro; responsivo → @frontend — 2026-06-18

### 6b — Detalhe do jogo (`GET /jogos/{id}`)
- [x] ✅ `services/jogos.py` — `detalhe_do_jogo(db, jogo_id, usuario, agora)`: retorna view com placar oficial, status, e palpites de todos **somente se** `prazo.palpites_de_terceiros_visiveis(...)` for True; caso contrário só o palpite do próprio usuário; seleção explícita de colunas → @backend — 2026-06-18
- [x] ✅ `app/routers/jogos.py` — `GET /jogos/{id}` (`Depends(get_current_user)`, 404 se inexistente) e registrado em `main.py` → @backend — 2026-06-18
- [x] ✅ `tests/test_jogos.py` — privacidade: terceiros ocultos enquanto rodada aberta; visíveis após fechar; inativos fora; ordenação por pontos; 404 jogo inexistente; auth (11 testes) → @backend — 2026-06-18
- [x] ✅ Tela `jogo_detalhe.html`: cabeçalho do jogo + placar oficial ("a definir" se sem gols); lista de palpites com pontos quando visível, senão aviso de privacidade; link de volta ao dashboard → @frontend — 2026-06-18

## Fase 7 — Admin (concluída — 2026-06-18)

Todas as rotas de admin protegidas (DECISÃO D6: anônimo → redirect `/login`; logado não-admin → 403).
Lógica de negócio só em `app/services/admin.py`; routers finos no padrão de `routers/palpites.py`.
Senha sempre via `app.services.auth.hash_senha`. Seleção explícita de colunas nos services.
Sem migração nova (modelos já cobriam os campos — D1 confirmada). Mutações via POST (D5).
Lançar resultado encerra só o jogo, não a rodada (D3). Reset define nova senha (D4).
Recálculo de pontos inclui palpites de inativos (D7, cache consistente).

### 7a — Rodadas (`/admin/rodadas`)
- [x] ✅ `services/admin.py` — `listar_rodadas`, `criar_rodada`, `atualizar_rodada`; valida `ordem` única (IntegrityError → ValueError) e `abertura <= fechamento`; estado calculado via `prazo.rodada_aberta_para_edicao` → @backend — 2026-06-18
- [x] ✅ `routers/admin.py` — `GET /admin/rodadas`, `POST /admin/rodadas`, `POST /admin/rodadas/{id}`; router registrado em `main.py` → @backend — 2026-06-18
- [x] ✅ `tests/test_admin_rodadas.py` — não-admin 403; anônimo → /login; criar; ordem duplicada falha; abrir/fechar; janela; `abertura > fechamento` rejeitado; inexistente → 404 → @backend — 2026-06-18

### 7b — Jogos + lançamento de resultado (`/admin/jogos`)
- [x] ✅ `services/admin.py` — `listar_jogos(db, rodada_id=None)`, `criar_jogo`, `atualizar_jogo`, `lancar_resultado`: grava gols, `status=ENCERRADO`, e **recalcula `Palpite.pontos` de TODOS os palpites do jogo** via `scoring.calcular_pontos` num único commit (idempotente) → @backend — 2026-06-18
- [x] ✅ `routers/admin.py` — `GET /admin/jogos` (filtro por rodada), `POST /admin/jogos`, `POST /admin/jogos/{id}`, `POST /admin/jogos/{id}/resultado` → @backend — 2026-06-18
- [x] ✅ `tests/test_admin_jogos.py` — não-admin 403; criar/editar; **recálculo correto** (9/6/4/3/0 conferidos no banco); relançar re-recalcula; status vira "encerrado"; inexistente → 404 → @backend — 2026-06-18

### 7c — Usuários (`/admin/usuarios`)
- [x] ✅ `services/admin.py` — `listar_usuarios`, `criar_usuario` (hash via `auth.hash_senha`, username duplicado → ValueError), `resetar_senha` (re-hash), `definir_ativo` → @backend — 2026-06-18
- [x] ✅ `routers/admin.py` — `GET /admin/usuarios`, `POST /admin/usuarios`, `POST /admin/usuarios/{id}/senha`, `POST /admin/usuarios/{id}/ativo` → @backend — 2026-06-18
- [x] ✅ `tests/test_admin_usuarios.py` — não-admin 403; criar (hash != senha; verificação bate); username duplicado rejeitado; resetar senha (login com a nova funciona); desativar bloqueia login → @backend — 2026-06-18

### 7d — Telas admin (`templates/admin/`)
- [x] ✅ Link "Admin" em `base.html` dentro de `{% if is_admin %}` (topbar nav) → @frontend — 2026-06-18
- [x] ✅ `templates/admin/rodadas.html` — lista com estado/janela, form criar, edição inline (toggle aberta + abertura/fechamento), estados vazio/erro → @frontend — 2026-06-18
- [x] ✅ `templates/admin/jogos.html` — filtro por rodada, criar/editar jogo, e form de **lançar resultado** com aviso de recálculo; estados vazio/erro → @frontend — 2026-06-18
- [x] ✅ `templates/admin/usuarios.html` — lista (ativo/admin), form criar, resetar senha e ativar/desativar; estados vazio/erro → @frontend — 2026-06-18

_Follow-up menor (não bloqueante): erros de validação em `/admin/jogos` hoje retornam HTTP 400 (página de erro padrão), enquanto rodadas/usuários re-renderizam com banner amigável. Uniformizar quando conveniente._

## Fase 8 — Importação inicial (concluída — 2026-06-18)

Escopo: só fase de grupos (linhas 2–73 da OFICIAL). 10 jogadores como não-admin com senha
temporária única; admin de gestão (`admin/admin123`) mantido à parte. Rodadas importadas
`aberta=False`. Pontos calculados via `scoring.calcular_pontos` (não reimplementa a LEGENDA).

- [x] ✅ `scripts/importar_planilha.py` — 10 usuários, 3 rodadas (grupos), 72 jogos (22 com resultado na 1ª), 480 palpites; idempotente (get-or-create); valida alinhamento times jogador×OFICIAL e aborta em divergência; auto-validação dos totais e vs coluna O → @backend — 2026-06-18
- [x] ✅ Validar a carga — QA reproduziu os 10 totais por jogador (Bernardo 44, Fernando 40, Gabriel 34, Gustavo 48, Marcio 67, Marques 63, Renan 26, Ricardo 47, Thiago 47, Soares 48) e 0 divergências vs coluna O; **APROVADA**, sem bloqueante → @qa — 2026-06-18

_Follow-ups do QA (não bloqueantes, ver HANDOFF):_
- _Re-rodar o importador reseta a senha de usuários já existentes — não resetar `senha_hash` de quem já existe (idempotência de credencial)._
- _Faltam testes de idempotência (rodar 2x) e de não-clobber do admin._
- _`Jogo` não tem `UniqueConstraint(rodada_id, time_casa, time_visitante)` — a idempotência de jogo é só por query; considerar nova migração Alembic._
- _Type hints fracos (`object`/`# type: ignore`) em `importar_planilha.py` — usar `Worksheet`/`Session`/`Callable`._

## Fase 9 — Fechamento (em andamento — 2026-06-18)

- [x] ✅ Revisão de QA do sistema inteiro (pontuação, prazo, privacidade, autorização, auth/sessão, segurança) — as 4 regras invioláveis centrais confirmadas corretas; achou 3 bloqueantes para deploy → @qa — 2026-06-18
- [x] ✅ Correção dos bloqueantes do QA → @backend — 2026-06-18:
  - Crash de timezone em `GET /palpites` (comparava aware×naive) — agora usa `prazo.palpites_de_terceiros_visiveis` (normaliza UTC); teste de regressão com `fechamento` naive.
  - `SECRET_KEY`: guard em `create_app` recusa subir com o padrão quando `DEBUG=0` (validado empiricamente).
  - Cookie de sessão endurecido: `SameSite=lax`, `HttpOnly`, `Secure` via `SESSION_HTTPS_ONLY`, `max_age` 14d.
  - Importantes: valida gols negativos no backend (`salvar_palpite`); `bcrypt<5.0` confirmado no `requirements.txt`.
  - Testes novos: regressão timezone, gols negativos, bordas de scoring (0x0→9, empate placar errado→6), autorização nas rotas admin POST. Suíte: **101 passando**.
- [x] ✅ Preparar deploy interno — `DEPLOY.md` (passos + checklist), `.env.example`, `README.md` atualizado (dev × produção, env vars). Rodar com `uvicorn app.main:app --env-file .env ...` → 2026-06-18
- [x] ✅ Preparar deploy em nuvem (Render + Neon) — `psycopg[binary]` no `requirements.txt`; `DATABASE_URL` normalizado para `postgresql+psycopg://` em `app/database.py` e `migrations/env.py`; `render.yaml` (Blueprint free); `.gitignore`; seção Render+Neon no `DEPLOY.md`. Suíte: **109 testes** → @backend — 2026-06-18
- [x] ✅ Repo no GitHub (`gcarlstron/copaphibra2026`, push da branch `main`) — 2026-06-18
- [x] ✅ Banco Neon criado, migrado e populado (admin + 10 jogadores + 3 rodadas + 72 jogos + 480 palpites; totais conferem) — 2026-06-18
- [x] ✅ Fix de portabilidade da migração (boolean `sa.false()/sa.true()`) para o Postgres da Neon — 2026-06-18
- [x] ✅ Web service no Render criado e no ar (Blueprint + `DATABASE_URL` da Neon), testado — 2026-06-19
- [ ] Pós-deploy: trocar senha do `admin`; (recomendado) rotacionar a senha do banco na Neon, pois foi compartilhada em texto

---

## Fase 10 — Resultados automáticos (ESPN) — concluída (2026-06-19)

Busca automática de resultados via API pública da ESPN (sem auth), disparada no login de
qualquer usuário, em background, com throttle persistido e isolamento total de erro. Reusa
`admin.lancar_resultado` (não reimplementa pontuação). Cruzamento por **abreviação FIFA**
via tabela de-para. Cliente HTTP: `httpx2` (`import httpx2 as httpx`). **155 testes passando.**
QA auditou (caminho crítico do login): veredito PRONTA, 2 importantes corrigidos.

### 10a — Throttle persistente (`sync_state`)
- [x] ✅ Model `SyncState` (`chave` única, `ultima_execucao`) + migração `7b24c90f7905` (revises a inicial) + `tests/test_sync_state.py` → @backend — 2026-06-19

### 10b — De-para de times (`team_alias`)
- [x] ✅ Model `TeamAlias` (`abreviacao` única, `nome` PT-BR, `nome_en`) + tabela na mesma migração + `scripts/seed_team_alias.py` idempotente (48 times, casa por acento-insensível com o banco) + `tests/test_team_alias.py` → @backend — 2026-06-19

### 10c — Cliente ESPN (`services/espn.py`)
- [x] ✅ `parse_eventos` (puro, tolerante; resolve home/away por `homeAway`) + `buscar_scoreboard`/`buscar_scoreboard_com_janela` (httpx2, timeout) + `tests/test_espn.py` (fixture real, MockTransport, sem rede) → @backend — 2026-06-19

### 10d — Service de sync (`services/sync_resultados.py`)
- [x] ✅ `sincronizar_resultados(db, agora)` — seleciona pendentes passados, 1 fetch por data (materializado, sem 2ª passagem), cruza por de-para, só FULL_TIME, reusa `lancar_resultado`, idempotente, loga ignorados; `tests/test_sync_resultados.py` (pontos recalculados, idempotência, home/away invertido, encerrado sem placar) → @backend — 2026-06-19

### 10e — Integração no login (background + throttle + erro isolado)
- [x] ✅ `disparar_sync_se_necessario(SessionLocal, agora)` (sessão própria, grava `ultima_execucao` antes da chamada, try/except amplo) + `config` (`espn_sync_intervalo_min`=15, `espn_timeout_s`=5) + `BackgroundTasks` no `POST /login` + `tests/test_login_sync.py` (login OK com ESPN caída, throttle dentro/fora da janela inclusive `ultima_execucao` naive) → @backend — 2026-06-19

### 10f — Validação das abreviações contra a ESPN
- [x] ✅ Validado ao vivo (datas 11–27/06): as 48 abreviações da ESPN batem com o de-para, 0 divergência. Fuso confirmado: `date(data_hora)` casa com `dates=` da ESPN (janela D-1/D/D+1 por robustez) → @backend — 2026-06-19

### Deploy da Fase 10
- [x] ✅ Migração `7b24c90f7905` aplicada na Neon + seed do de-para (48) na Neon — 2026-06-19
- [ ] Push do código (dispara deploy no Render) — o sync passa a rodar no login em produção
- [ ] (Opcional, decidir) backfill imediato: rodar o sync uma vez na Neon, ou deixar o 1º login preencher

### 10g — UI (opcional, fora do MVP)
- [ ] (Opcional) Indicador "última atualização de resultados" no dashboard, lendo `sync_state.ultima_execucao` → @frontend

### Ajuste (2026-06-19): gatilho do sync movido para o dashboard
- [x] ✅ O sync ESPN passa a ser disparado ao carregar o dashboard (`GET /`), não mais no `POST /login` — cobre quem mantém a sessão aberta e só recarrega a home. Mesmo padrão (BackgroundTask + `SessionLocal` + throttle persistido); só para usuário autenticado. `BackgroundTasks` removido de `routers/auth.py`; `routers/dashboard.py` ganha o disparo. Testes movidos `test_login_sync.py` → `test_dashboard_sync.py` (dispara/falha-isolada/anônimo-não-dispara/sessão-própria/login-não-dispara-mais + throttle). **183 testes** → @backend — 2026-06-19

---

## Fase 11 — Lista de jogos + escudos (concluída — 2026-06-19)

Duas melhorias: (1) página `GET /jogos` com TODOS os jogos + os pontos do PRÓPRIO usuário
ao lado de cada um; (2) escudos dos times (ESPN) no detalhe e na lista. Regra 4 reafirmada:
a lista só carrega os pontos do próprio usuário. **177 testes passando.**

### 11a — Escudos: migração + seed (`team_alias.escudo_url`)
- [x] ✅ Migração `a1b2c3d4e5f6` (down_revision `7b24c90f7905`) adiciona `escudo_url` String(255) nullable; campo no model; `seed_team_alias.py` popula derivando `https://a.espncdn.com/i/teamlogos/countries/500/{abrev}.png` (idempotente); `tests/test_team_alias.py` → @backend — 2026-06-19
- [x] ✅ Deploy: migração + re-seed aplicados na Neon (48 times com escudo_url, 0 sem) → @backend — 2026-06-19

### 11b — Backend: escudos no detalhe
- [x] ✅ `detalhe_do_jogo` ganha `escudo_casa`/`escudo_visitante` (LEFT JOIN em `team_alias`; None se ausente); `tests/test_jogos.py` (presente/ausente/null) → @backend — 2026-06-19

### 11c — Backend: lista "Todos os jogos" (`GET /jogos`)
- [x] ✅ `listar_todos_os_jogos(db, usuario)` — `JogoListaItem`/`RodadaGrupo`/`JogosListaData`, agrupado por `Rodada.ordem` (jogos por `data_hora`), com escudos e `meus_pontos` (só do próprio usuário, None se não palpitou); 2 queries (sem N+1) → @backend — 2026-06-19
- [x] ✅ `GET /jogos` (protegida, anônimo→/login; coexiste com `/jogos/{id}`); `tests/test_jogos_lista.py` (15 testes: pontos corretos/None, ordem, escudo ausente, login, privacidade) → @backend — 2026-06-19

### 11d — Frontend
- [x] ✅ `jogos_lista.html` — todos os jogos por rodada, escudos, e pontos do usuário ao lado (badge 9/6/4/3/0; "—" sem palpite; "aguardando" sem resultado); responsivo → @frontend — 2026-06-19
- [x] ✅ Escudos no `jogo_detalhe.html` (lazy/alt/onerror, fallback se None) + link "Jogos" no menu (`base.html`) → @frontend — 2026-06-19
- [ ] (Opcional, não feito) escudos nas listas do dashboard — exigiria expor `escudo_url` em `JogoResumoView` (`services/dashboard.py`); pulado por ora

### Deploy da Fase 11
- [ ] Push do código (junto com a Fase 10) → dispara deploy no Render. Migração `a1b2c3d4e5f6` e seed já aplicados na Neon.

---

## Fase 12 — Troca de senha pelo próprio usuário (concluída — 2026-06-19)

Autoatendimento: qualquer usuário logado troca a própria senha (até hoje só o admin
resetava via `/admin/usuarios`). Lógica em `services/auth.py`; senha sempre com hash.
**183 testes passando.**

- [x] ✅ `services/auth.py` — `alterar_senha(db, usuario, senha_atual, nova_senha, confirmacao)`: valida senha atual, tamanho mínimo (`SENHA_MIN_LENGTH=6`), confirmação e que a nova ≠ atual; `ValueError` (pt-BR) em falha; re-hash via `hash_senha` num commit → @backend — 2026-06-19
- [x] ✅ `routers/auth.py` — `GET /trocar-senha` (form, anônimo→/login) e `POST /trocar-senha` (re-renderiza com banner de erro 400 ou sucesso); helper `_templates()` → @backend — 2026-06-19
- [x] ✅ `tests/test_auth.py` — sucesso (novo hash bate, antigo não); senha atual incorreta; confirmação diferente; nova curta; nova igual à atual; exige login (GET+POST) — 6 testes → @backend — 2026-06-19
- [x] ✅ `templates/trocar_senha.html` (reusa estilos `auth-*`) + link "Trocar senha" no `base.html` + estilos `.auth-message` (erro/ok) no `app.css` → @frontend — 2026-06-19
- [ ] Push do código → dispara deploy no Render

---

## Backlog / Fase 2 (futuro)

- [ ] Notificação de "falta palpitar" antes do fechamento da rodada
- [ ] Histórico de copas anteriores (aba `TODAS AS COPAS`)
