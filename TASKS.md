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

### 10g — UI (concluída — 2026-06-22)
- [x] ✅ Indicador "Resultados atualizados há X min" no dashboard, lendo `sync_state.ultima_execucao`. `montar_dashboard` expõe `ultima_sync` + `ultima_sync_texto` (helper puro `_descrever_ultima_sync`: agora/min/h/d, normaliza naive→UTC, futuro→"agora mesmo"); badge discreto (ponto verde) no cabeçalho da classificação (`dashboard.html` + `.sync-status` no `app.css`); 4 testes novos em `test_dashboard.py` → @backend + @frontend — 2026-06-22

### Ajuste (2026-06-19): gatilho do sync movido para o dashboard
- [x] ✅ O sync ESPN passa a ser disparado ao carregar o dashboard (`GET /`), não mais no `POST /login` — cobre quem mantém a sessão aberta e só recarrega a home. Mesmo padrão (BackgroundTask + `SessionLocal` + throttle persistido); só para usuário autenticado. `BackgroundTasks` removido de `routers/auth.py`; `routers/dashboard.py` ganha o disparo. Testes movidos `test_login_sync.py` → `test_dashboard_sync.py` (dispara/falha-isolada/anônimo-não-dispara/sessão-própria/login-não-dispara-mais + throttle). **183 testes** → @backend — 2026-06-19

### Ajuste (2026-06-22): sync ESPN passa a ser SÍNCRONO no dashboard
- [x] ✅ Antes o sync rodava como `BackgroundTask` (depois da resposta), então a 1ª carga mostrava dados antigos e só após F5 apareciam os novos. Agora o `GET /` chama `sincronizar_se_necessario(db, agora, deadline=...)` de forma **síncrona, ANTES** de `montar_dashboard`, na própria sessão do request — a classificação/jogos já saem atualizados na 1ª carga. Fallback preservado: `try/except` no router + erros da ESPN engolidos → renderiza com os dados do banco se a API não responder. `deadline` (`ESPN_SYNC_DEADLINE_S=8`) limita o tempo de espera (relógio monotônico) propagado a `buscar_scoreboard_com_janela`/`sincronizar_resultados`; throttle de 15 min mantido (só o 1º acesso da janela paga o fetch). `disparar_sync_se_necessario` mantido como wrapper de background/standalone (abre sessão própria + isola erro). `test_dashboard_sync.py` atualizado (chamada síncrona/falha-isolada/anônimo/recebe-sessão+deadline/login-não-dispara + throttle). **183 testes** → @backend — 2026-06-22

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
- [x] ✅ Remoção do `passlib`: `app/services/auth.py` passa a usar a lib `bcrypt` diretamente (`hashpw`/`checkpw`/`gensalt`). Motivo: `passlib` 1.7.4 é incompatível com Python 3.13+ (módulo `crypt` removido) e disparava `(trapped) error reading bcrypt version` com bcrypt >= 4.1. Hash `$2b$` idêntico — hashes legados seguem válidos (verificado). `requirements.txt`: `bcrypt>=4.0,<5.0` (passlib removido); docs atualizadas (CLAUDE/DEPLOY/HANDOFF). **183 testes, 0 avisos** → @backend — 2026-06-19
- [ ] Push do código → dispara deploy no Render

---

## Fase 13 — Estados do jogo ao vivo + atualização automática (concluída — 2026-06-19)

Jogos passam a ter 4 estados (`agendado`, `em_andamento`, `intervalo`, `encerrado`),
detectados via ESPN. Enquanto a bola rola, o sync busca mais rápido e a página atualiza
sozinha. Sem migração (`status` String(20) comporta os valores novos). **198 testes passando.**

- [x] ✅ `services/espn.py` — `EventoEspn` ganha `estado` (`type.state`: pre/in/post, default "") + propriedades `ao_vivo`/`no_intervalo` (com fallback por `type.name` quando `state` ausente); constantes `ESPN_STATUS_HALFTIME`/`SCHEDULED`, `ESPN_STATE_*` → @backend — 2026-06-19
- [x] ✅ `services/dashboard.py` — constantes `STATUS_EM_ANDAMENTO`/`STATUS_INTERVALO`/`STATUS_AO_VIVO`; `_montar_jogos_ao_vivo` + campo `jogos_ao_vivo` em `DashboardData` (excluídos de recentes/próximos por status) → @backend — 2026-06-19
- [x] ✅ `services/sync_resultados.py` — passo 5b atualiza status/placar de jogos ao vivo **sem pontuar** (só FULL_TIME→`lancar_resultado` pontua); idempotente; contador `atualizados_ao_vivo`. Throttle **dinâmico**: `_intervalo_efetivo_min` usa intervalo curto (`espn_sync_intervalo_ao_vivo_min`=1) quando há jogo ao vivo/iniciado há <3h, senão 15 min → @backend — 2026-06-19
- [x] ✅ `config.py` — `espn_sync_intervalo_ao_vivo_min` (1) e `auto_refresh_ao_vivo_s` (60) → @backend — 2026-06-19
- [x] ✅ Auto-refresh: `base.html` recarrega a cada `auto_refresh_s`s quando a flag é passada; rotas `/`, `/jogos`, `/jogos/{id}` passam a flag só quando há jogo ao vivo na página → @backend + @frontend — 2026-06-19
- [x] ✅ `templates/macros.html` — macro `status_pill(status)` reusado em dashboard/lista/detalhe/admin; seção "Ao vivo agora" no dashboard; CSS `.status-pill--ao-vivo` (ponto pulsante), `--intervalo`, `.live-card`, `.result-row--live` → @frontend — 2026-06-19
- [x] ✅ Testes: `test_espn.py` (estado/ao_vivo/intervalo/fallback); `test_sync_resultados.py` (atualiza ao vivo sem pontuar, intervalo, idempotência, ao vivo→encerra→pontua, throttle dinâmico); `test_dashboard.py` (jogos_ao_vivo) — +15 testes → @backend — 2026-06-19
- [ ] Push do código → dispara deploy no Render

---

## Fase 13 — Privacidade dos palpites: verificação + endurecimento (concluída — 2026-06-22)

Regra inviolável #4: enquanto a rodada está **aberta** para palpite, um jogador **não vê o
palpite dos outros**; só depois que a rodada **fecha** todos veem os de todos.

- [x] ✅ **Auditoria de QA (read-only) — veredito PRIVACIDADE OK:** nenhum caminho expõe o **placar palpitado** de terceiros com a rodada aberta. A gating é feita escolhendo *qual query roda* no service (o dado sensível nem sai do banco), em todas as superfícies: `detalhe_do_jogo` (via `palpites_de_terceiros_visiveis`), `listar_todos_os_jogos`/`listar_palpites_do_usuario` (query amarrada a `usuario_id`), dashboard (só agrega `pontos`, nunca o placar), admin (sem bypass — admin também não vê), HTMX (só `204 + redirect`). Bordas de `palpites_de_terceiros_visiveis` validadas (agendada/sem janela/fechamento passado-futuro/naive). **Decisão confirmada:** admin segue sujeito à privacidade (sem bypass) → @qa — 2026-06-22
- [x] ✅ **Endurecimento do Risco #1 (pontos no ranking):** `_montar_classificacao` agora só soma `Palpite.pontos` de jogos cuja rodada **não** está aberta para edição (`_rodadas_abertas_para_edicao_ids` + JOIN em `Jogo`). Fecha a brecha de um jogo encerrado dentro de uma rodada ainda aberta (lançar resultado não fecha a rodada — D3) revelar via bucket/total que o jogador pontuou antes de a rodada fechar. No fluxo normal é no-op (palpite de rodada aberta vale 0). Testes: `test_dashboard.py` (rodada aberta→0 pts / fechada→conta) + 3 bordas em `test_prazo.py`. **192 testes** → @backend — 2026-06-22

_Follow-ups menores do QA (não bloqueantes):_
- _`services/jogos.py` ramo do "próprio palpite" não filtra `Usuario.ativo` (inofensivo — usuário sempre vê o próprio)._
- _`services/palpites.py` calcula `terceiros_visiveis` mas o template `palpites.html` não usa (campo morto; remover ou documentar)._

## Fase 14 — Melhorias de UX dos painéis (concluída + no ar — 2026-06-22)

Frontend puro (sem backend). **Implementada e no ar** (deploy `b2436ee`, PR #3). Conforme
o detalhamento abaixo (14a/14b feitos). **Ajuste do usuário pós-deploy:** o recolhível foi
mantido em "Ao vivo agora" e "Classificação geral" e **removido** de "Últimos resultados" e
"Próximos jogos" (lado a lado na grade não ficou bom) — esse ajuste está no commit `fix:` da
branch `chore/follow-ups-qa` (ver Fase 15), ainda **não** no ar.

> Incidente de deploy (2026-06-22): após o merge, o navegador servia `app.css` antigo (sem as
> regras de recolhível) → parecia que "não minimizava". Causa: falta de cache-busting + cache do
> Render. Render resolvido com **restart do serviço**; o cache do navegador fica para a Fase 15.

Duas melhorias na experiência das telas do jogador.

### 14a — Painéis recolhíveis ("minimizar" para uma linha)
Todo painel `round-card` pode ser **recolhido** para mostrar só o cabeçalho (uma linha),
para a pessoa esconder o que não quer ver no momento. Vale para todos os cards que hoje
usam o mesmo padrão `<article class="round-card"><header class="round-head">…`:
- **Dashboard** (`dashboard.html`): Classificação geral, Últimos resultados, Próximos jogos.
- **Todos os jogos** (`jogos_lista.html`): um card por rodada (1ª, 2ª, 3ª…).
- **Meus palpites** (`palpites.html`): um card por rodada.
- (Fora do escopo por ora: cards do `admin/`.)

Abordagem (parametrizada por **classe**, decidida com o usuário 2026-06-22):
- [ ] Recolhibilidade é **opt-in por classe**: `round-card--collapsible`. Um painel só recolhe se tiver a classe — para desativar, basta não pô-la (hoje vai em todos os 5). Mantém a casca `<article class="round-card">` intacta (sem converter para `<details>`), só acrescenta a classe + `data-panel-id` estável.
- [ ] `static/js/ui.js` (incluído no `base.html`) varre `.round-card--collapsible`, injeta um chevron no `.round-head`, torna o cabeçalho clicável (com `role=button`/`tabindex`/`aria-expanded` e teclado Enter/Espaço), e alterna a classe `is-collapsed` no card. Ignora cliques em `a/button/input/form/label` dentro do header.
- [ ] CSS: `.round-card.is-collapsed > :not(.round-head) { display:none }` (vira uma linha); chevron posicionado de forma absoluta (não desarruma o elemento à direita do header) e girando no estado recolhido.
- [ ] **Persistir** por painel em `localStorage` (`data-panel-id`, ex.: `dashboard:classificacao`) — senão todo reload (o dashboard recarrega ao sincronizar) reabre tudo. Fallback sem JS: painel aberto (comportamento atual).

### 14b — "Próximos jogos" clicável (vai pro detalhe do jogo)
- [ ] No `dashboard.html`, a seção **Próximos jogos** usa `<div class="upcoming-row">` (não clicável). Trocar por `<a href="/jogos/{{ jogo.jogo_id }}">` como já é em "Últimos resultados" (`result-row`), ajustando o CSS (`.upcoming-row` → estado clicável/hover). O `jogo_id` já vem no `JogoResumoView`, então é só template + CSS.

## Fase 15 — Follow-ups técnicos/QA (concluída — 2026-06-22 — branch `chore/follow-ups-qa`)

Branch `chore/follow-ups-qa` (a partir da `main` pós-deploy). Inclui também o ajuste dos cards
(commit `fix:`). **213 testes.** **Deploy desta fase exige a migração `d4e5f6a7b8c9` na Neon**
(`alembic upgrade head`).

- [x] ✅ **Cache-busting dos estáticos:** `?v={{ asset_version }}` em app.css/ui.js no `base.html`; `Settings.asset_version` = `RENDER_GIT_COMMIT[:12]` (prod, muda a cada deploy) ou mtime de app.css/ui.js (dev); global injetado no `_templates()` dos 5 routers → 2026-06-22
- [x] ✅ **Importador idempotente na senha:** `_get_or_create_usuario` só seta `senha_hash` ao CRIAR; em existente atualiza só nome/ativo (preserva a senha trocada, não toca `is_admin`). + testes unit → 2026-06-22
- [x] ✅ **Importador preserva jogos encerrados:** `_get_or_create_jogo` não sobrescreve jogo já ENCERRADO (resultado autoritativo, pode vir da ESPN/admin) → `protegido=True`; palpites desses jogos também não são reescritos (evita pontos divergentes). Rodadas já eram preservadas (só `nome` atualiza). + testes _(pedido do usuário)_ → 2026-06-22
- [x] ✅ **Remover campo morto `terceiros_visiveis`** de `services/palpites.py`; regressão de timezone (`GET /palpites` com fechamento naive → 200) segue coberta por `rodada_aberta_para_edicao` → 2026-06-22
- [x] ✅ **`UniqueConstraint(rodada_id, time_casa, time_visitante)` em `Jogo`:** `__table_args__` no model + migração `d4e5f6a7b8c9` (modo batch: SQLite recria, Postgres/Neon faz ALTER direto); testada upgrade→downgrade→upgrade; + teste de IntegrityError. **Deploy:** `alembic upgrade head` na Neon (falha se houver duplicatas — improvável, get-or-create) → 2026-06-22
- [x] ✅ **Type hints do importador:** `Session`/`Worksheet`/`Callable` no lugar de `object`/`# type: ignore` em `importar_planilha.py` → 2026-06-22
- [ ] (Menor, opcional — NÃO bloqueia) filtrar `Usuario.ativo` no ramo do "próprio palpite" em `services/jogos.py` (inofensivo: o usuário sempre vê o próprio palpite).

_Deploy da Fase 15: merge da PR → Render builda → roda `alembic upgrade head` (startCommand) que
aplica `d4e5f6a7b8c9` na Neon automaticamente. As demais mudanças são código/estáticos._

## Fase 16 — Backlog de ajustes (revisão architect + QA — 2026-06-22)

Revisão de fechamento (read-only) pelos agentes **architect** e **qa** sobre a `main` pós Fases 10–15.
Veredito: sistema **saudável e bem testado**, 4 regras invioláveis íntegras, **nenhum bloqueante**.
Os itens abaixo são ajustes/dívida para priorizar depois. Lente: app interno ~10 usuários.

> **2026-06-23 — lote "quick wins de robustez" concluído** (branch `fix/fase16-quick-wins`, +7 testes, **220 passando**): login 500 com hash malformado → 401, limite de 72 bytes do bcrypt, criar/editar jogo duplicado → 400, sync ao vivo não sobrescreve placar bom com `None`, imports não usados removidos.

### ALTA
- [x] ✅ **Login quebra (HTTP 500) com `senha_hash` malformado** _(QA — bug real, quick win)_ — feito 2026-06-23. — `services/auth.py:22-24`: `bcrypt.checkpw` levanta `ValueError("Invalid salt")` p/ hash vazio/legado/corrompido; `verificar_senha`/`alterar_senha` não tratam → 500 no login em vez de 401. **Ação:** try/except em `checkpw` → `False`. + teste.
- [x] ✅ **ADR-001 — sync ESPN síncrono no `GET /` no pico de jogo ao vivo** _(architect — decisão)_ — feito 2026-06-23. **Decisão: manter síncrono + endurecer** (mantém a 1ª carga fresca, ganho da Fase 13; desacoplar reintroduziria o atraso na 1ª carga). Implementado: (1) `deadline` agora também é checado nas fases de **escrita** (passos 5 e 5b) — não só no fetch; (2) **throttle atômico** via compare-and-set (`_reivindicar_slot`: `UPDATE ... WHERE ultima_execucao = <valor lido>`) → em acessos simultâneos (várias abas no auto-refresh), só 1 requisição bate na ESPN, eliminando fetches duplicados. +tests (CAS + deadline na escrita). — `routers/dashboard.py` + `sync_resultados.py`: com throttle de 1 min ao vivo + auto-refresh de 60s, cada recarga vira fetch+escrita externos bloqueando o render (até `deadline`=8s) no momento de maior uso; o `deadline` só é checado entre fetches (passo 4), **não na fase de escrita** (`lancar_resultado` comita por jogo); e há corrida de throttle (sessões separadas → fetches duplicados). **Ação:** decidir — desacoplar render do fetch (página lê do banco + auto-refresh; fetch em background/throttle único com `UPDATE` condicional) **vs** manter síncrono + checar `deadline` no laço de escrita (paliativo).
- [~] **Lacuna de teste no caminho `deadline` do sync** _(QA)_ — `sync_resultados.py:136-141` e `espn.py` sem teste de "deadline estourado → pula datas / para no meio da janela D-1/D/D+1". **Ação:** testes com monkeypatch de `time.monotonic`. _Parcial (2026-06-23): cobertos o skip de datas no fetch e o novo guard na escrita (`TestDeadline`). Falta o "para no meio da janela D-1/D/D+1" dentro de `espn.py` (`buscar_scoreboard_com_janela`)._

### MÉDIA
- [x] ✅ **ADR-002 — fuso BRT rotulado como UTC** _(architect)_ — feito 2026-06-23. **Decisão:** alinhar o "agora" ao fuso dos dados (Abordagem A), **não** reescrever os dados p/ UTC real (Abordagem B descartada: quebraria o casamento de datas com a ESPN, que agrupa por `date(Jogo.data_hora)` no calendário BRT). Novo `app/services/tempo.py` (`FUSO_DADOS=UTC-3` fixo, sem tzdata; `agora()`/`em_fuso_dos_dados()`); todos os pontos de comparação (services dashboard/admin/palpites/jogos + routers `/`, `/palpites`, `/jogos`) passam a usar `agora()` em vez de `datetime.now(timezone.utc)`. Throttle do sync tolera diferença negativa (transição da `ultima_execucao` legada pós-deploy). `tests/test_tempo.py` com cenário de mata-mata. Admin segue digitando hora BRT (já gravada como BRT-rotulado-UTC — consistente). — `models/jogo.py`/`rodada.py` + `espn.py`: horários da planilha são BRT mas comparados com `datetime.now(timezone.utc)` → deslocamento de ~3h na detecção de "ao vivo/iminente" e na lógica de prazo. Inofensivo na fase de grupos (coincidência), **risco no mata-mata**. **Ação:** alinhar "agora" ao fuso dos dados (ou normalizar dados p/ UTC real) + teste do mata-mata.
- [x] ✅ **bcrypt trunca senha > 72 bytes silenciosamente** _(QA)_ — feito 2026-06-23 (valida `<= 72` bytes em `hash_senha`/`alterar_senha`; `verificar_senha` não propaga). — `services/auth.py:13-24`: bytes após o 72º ignorados (segurança); e `alterar_senha` daria falso "senha igual" p/ senhas que só diferem após o byte 72. **Ação:** validar `len(senha.encode()) <= 72`.
- [ ] **Jogo "preso" ao vivo sem reversão** _(QA)_ — `sync_resultados.py`: se a ESPN parar de reportar um jogo sem `FULL_TIME` (ou abrev. sem de-para), ele fica `em_andamento` para sempre no dashboard. Recuperável só pelo admin. **Ação:** encerrar/filtrar jogos ao vivo "vencidos" há > N horas.
- [ ] **Rodada `aberta=False` sem fechamento "revela" terceiros** _(QA — privacidade, semântica frágil)_ — `prazo.palpites_de_terceiros_visiveis:54-55` retorna True p/ `aberta=False, fechamento=None` (intencional p/ rodadas importadas/encerradas). Se o admin cria rodada nova e cadastra jogos antes de abrir, `detalhe_do_jogo` exporia palpites (na prática vazio — ninguém palpitou numa rodada nunca aberta; risco baixo). **Ação:** "revelado" exigir fechamento passado/flag explícito de encerrada; ou documentar a ordem (abrir antes de cadastrar) + teste.
- [ ] **`alembic upgrade head` no `startCommand` derruba o serviço se a migração falhar** _(architect)_ — `render.yaml:7`: migração quebrada = home fora do ar. **Ação:** documentar no DEPLOY.md; idealmente release hook do Render separado do start. Não bloqueante.

### BAIXA / quick wins
- [x] ✅ **`criar_jogo`/`atualizar_jogo` não tratam a `UniqueConstraint` nova** _(QA — consequência da Fase 15)_ — feito 2026-06-23 (router de `atualizar_jogo` agora distingue 404 × 400). — `services/admin.py`: criar jogo duplicado (mesma rodada+times) → 500 em vez de 400 amigável. **Ação:** capturar `IntegrityError` → `ValueError` (400). + teste.
- [x] ✅ **Atualização ao vivo pode sobrescrever placar bom com `None`** _(QA)_ — feito 2026-06-23. — `sync_resultados.py:259-261`: só atualizar gols se `ev.gols_casa`/`gols_visitante` não forem None.
- [x] ✅ **Imports não usados** _(QA — ruff)_ — `field` em `dashboard.py`/`sync_resultados.py`, `func` em `dashboard.py` removidos — feito 2026-06-23.
- [ ] **`_templates()` duplicado em 5 routers + `Jinja2Templates` por request** _(architect)_ — extrair p/ um `app/templating.py` único com as globals (`asset_version`). ~20 min, baixo risco.
- [ ] **`_parse_score` definido dentro do loop em `parse_eventos`** _(architect)_ — `espn.py:128-132`: mover p/ módulo. Trivial.

### NÃO vale mexer (consenso architect + qa — evitar over-engineering p/ ~10 usuários)
- Mais índices (já há nas FKs + `data_hora`/`ordem`/`chave`); schemas Pydantic formais (YAGNI até haver payload JSON); Enum/CHECK p/ `status`; advisory locks/Redis p/ o throttle; filtrar `Usuario.ativo` no ramo do "próprio palpite" (inofensivo).
- `httpx2` confirmado como dependência legítima (Pydantic Services / Tom Christie), **não** é typosquat.

## Backlog / Fase 2 (futuro)

- [ ] **Exportar dados para Excel (.xlsx)** — resultado geral (classificação), jogos e palpites.
  _A definir: gerar via rota admin (download) ou via script; uma aba por seção (Classificação / Jogos / Palpites); reusar `openpyxl` (já no `requirements.txt`). Hoje existe o `scripts/relatorio.py` (read-only, só console) como base da leitura desses mesmos dados — pensar melhor no formato/entrega depois._
- [ ] **Painéis de BI do Grafana** — desempenho por jogador e geral. Datasource: o Grafana lê o **mesmo Postgres (Neon)** via **role read-only** dedicado (não a credencial da app). Roadmap em 3 passos:
  - [ ] _**Passo 1 (agora) — Grafana Cloud free, um dashboard por usuário** (manual) com as estatísticas de cada jogador. "Um por usuário" porque no Cloud free o public dashboard não deixa o visitante trocar a variável nem expor `$jogador` no link. Dica: usar variável **Constant** `jogador` por dashboard + queries com `'$jogador'` (facilita a migração pro dash único depois)._
  - [ ] _**Passo 2 — self-hosted via Docker** na máquina + **Cloudflare Tunnel**; primeiro tunelar **só o Grafana** pra teste (app/banco ficam onde estão; app é sensível a prazo → evitar indisponibilidade no deadline)._
  - [ ] _**Passo 3 — migrar pro Grafana self-hosted e consolidar num dashboard único** com `$jogador`. Aí abre embed por painel (`<iframe>` `d-solo`) no app (`GET /estatisticas`, protegida): self-hosted OSS destrava `auth.anonymous` + `allow_embedding=true`, que o Cloud bloqueia._
  - _Privacidade: dash por usuário mostra só o próprio jogador (ok). No dash geral, não exibir placares de terceiros com a rodada aberta — filtrar `WHERE NOT r.aberta`._
- [ ] Notificação de "falta palpitar" antes do fechamento da rodada
- [ ] Histórico de copas anteriores (aba `TODAS AS COPAS`)
