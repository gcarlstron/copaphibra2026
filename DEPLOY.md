# Deploy interno — Copa Phibra 2026

Guia para subir o bolão para uso interno (~10 jogadores). App único FastAPI server-rendered.

Duas opções abaixo: **Opção A — Render + Neon** (nuvem, grátis, recomendada) e
**Opção B — servidor próprio / VM**.

---

# Opção A — Render (nuvem, free) + Neon (Postgres free)

O free tier do Render tem **disco efêmero** (apaga o arquivo a cada deploy/restart), então
**não** usamos SQLite em produção — o banco é um **Postgres gerenciado na Neon** (grátis e
sem expirar). O código já está pronto: o `DATABASE_URL` é normalizado para `postgresql+psycopg://`
automaticamente, e o `render.yaml` na raiz descreve o serviço.

### A1. Criar o banco na Neon
1. Crie conta em https://neon.tech (free) e um projeto (região mais próxima, ex.: US East).
2. Copie a **connection string** (formato `postgresql://usuario:senha@host/db?sslmode=require`).
   Guarde — será o `DATABASE_URL` no Render. (Não precisa trocar o prefixo; o app normaliza.)

### A2. Subir o código para o GitHub
O Render faz deploy a partir de um repositório Git. Em um **repositório privado** (o app é interno):
```bash
git init
git add .
git commit -m "chore: deploy inicial Copa Phibra"
git branch -M main
git remote add origin https://github.com/<voce>/<repo>.git
git push -u origin main
```
> O `.gitignore` já exclui `.venv/`, `*.db` e `.env`. A planilha em `import/` **é** versionada —
> mantenha o repositório **privado** (são dados dos jogadores).

### A3. Criar o serviço no Render
1. Em https://render.com (login com o GitHub), **New → Blueprint** e selecione o repositório.
   O Render lê o `render.yaml` e cria o web service `copa-phibra` (plano free).
   - Alternativa sem Blueprint: **New → Web Service**, runtime Python,
     Build: `pip install -r requirements.txt`,
     Start: `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
2. Em **Environment**, defina as variáveis:
   - `DATABASE_URL` → a connection string da Neon (passo A1). *(no Blueprint vem marcada como "sync: false" — preencha manualmente.)*
   - `SECRET_KEY` → o Blueprint **gera** um valor seguro automaticamente; se criar manual, gere com `python -c "import secrets; print(secrets.token_hex(32))"`.
   - `DEBUG=0`, `SESSION_HTTPS_ONLY=1` (o Render serve HTTPS), `PYTHON_VERSION=3.11.9` (já no `render.yaml`).
3. **Create** / **Apply**. No primeiro deploy, o `startCommand` roda `alembic upgrade head` e cria as tabelas no Postgres da Neon.

### A4. Carga inicial dos dados (admin + planilha)
O free tier não tem shell, então rode os scripts **da sua máquina apontando para a Neon**:
```bash
# Windows PowerShell:  $env:DATABASE_URL="postgresql://...neon..."
# bash:                export DATABASE_URL="postgresql://...neon..."
python -m alembic upgrade head          # (se ainda não rodou no deploy)
python scripts/criar_admin.py           # cria admin/admin123 NO banco da Neon
python scripts/importar_planilha.py     # carrega jogadores/rodadas/jogos/palpites
python scripts/seed_team_alias.py       # popula o de-para de times (48) p/ o sync da ESPN
```
(O app normaliza o `DATABASE_URL`, então a string crua da Neon funciona nos scripts também.)

> **Resultados automáticos (ESPN):** a partir da Fase 10, ao logar o app busca em background
> os resultados que faltam (sem bloquear o login). Exige o `team_alias` semeado (`seed_team_alias.py`).
> Opcional: ajustar `ESPN_SYNC_INTERVALO_MIN` (throttle, default 15) e `ESPN_TIMEOUT_S` (default 5).
> Se um dia recriar o banco do zero, rode o `seed_team_alias.py` de novo.

### A5. Finalizar
- Acesse a URL do Render (`https://copa-phibra.onrender.com` ou similar), entre com `admin`/`admin123`.
- **Troque a senha do admin** em Admin → Usuários → Resetar senha.
- Observação: no free tier o serviço **hiberna após ~15 min ocioso**; a primeira visita depois disso demora ~30-60s para "acordar". Normal para uso esporádico.

---

# Opção B — Servidor próprio / VM

## 1. Pré-requisitos

- Python 3.11+
- Acesso ao servidor/máquina interna onde o app vai rodar

## 2. Instalação

```bash
python -m venv .venv
.venv/Scripts/activate        # Windows (PowerShell: .venv\Scripts\Activate.ps1)
# source .venv/bin/activate   # Linux/macOS
pip install -r requirements.txt
```

> `requirements.txt` fixa `bcrypt<5.0` — necessário para o hash de senha (passlib) funcionar.

## 3. Variáveis de ambiente

Copie `.env.example` para `.env` e ajuste. As variáveis:

| Variável | Obrigatória | Padrão | Descrição |
|---|---|---|---|
| `SECRET_KEY` | **sim em produção** | `dev-secret-change-me` | Assina o cookie de sessão. Em produção (`DEBUG=0`) o app **se recusa a subir** com o valor padrão. Gere um valor forte (abaixo). |
| `DEBUG` | não | `0` | `0` = produção; `1` = dev (stack traces, cookie relaxado, ignora a checagem do `SECRET_KEY`). |
| `DATABASE_URL` | não | `sqlite:///./copa_phibra.db` | SQLite por padrão; pronto para PostgreSQL. |
| `SESSION_HTTPS_ONLY` | não | `0` | `1` marca o cookie como `Secure` (use atrás de HTTPS). Mantenha `0` se o acesso interno for por HTTP simples. |

Gerar um `SECRET_KEY` forte:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

## 4. Banco de dados

```bash
python -m alembic upgrade head
```

## 5. Carga inicial dos dados

Criar o usuário administrador (gestão de rodadas/jogos/usuários):

```bash
python scripts/criar_admin.py            # admin / admin123 (TROCAR a senha depois)
# ou: python scripts/criar_admin.py <usuario> <senha> "<Nome>"
```

Importar a planilha (jogadores, rodadas de grupos, jogos, resultados e palpites):

```bash
python scripts/importar_planilha.py
```

> O importador é idempotente para a estrutura. **Atenção:** hoje ele reaplica a senha
> temporária dos jogadores a cada execução — não rode de novo depois que os jogadores
> trocarem a senha (ver follow-up em `HANDOFF.md`).

## 6. Subir o servidor

Produção (sem `--reload`, escutando na rede interna):

```bash
uvicorn app.main:app --env-file .env --host 0.0.0.0 --port 8000
```

O uvicorn carrega o `.env` para o ambiente antes de iniciar o app. Para rodar como
serviço, use o gerenciador de processos do sistema (systemd, NSSM no Windows, etc.)
definindo as mesmas variáveis de ambiente.

Healthcheck: `GET /healthz` → `{"status": "ok"}`.

## 7. Pós-deploy (checklist)

- [ ] `SECRET_KEY` forte definido (e **não** o padrão).
- [ ] `DEBUG=0`.
- [ ] Senha do `admin` trocada (o padrão `admin123` é só para o primeiro acesso) — via **Admin → Usuários → Resetar senha**.
- [ ] Senha temporária dos jogadores comunicada/trocada conforme necessário.
- [ ] `SESSION_HTTPS_ONLY=1` se estiver atrás de HTTPS.
- [ ] Testar login, lançamento de resultado (recalcula pontos) e classificação.

## Notas de segurança

- Cookie de sessão: `HttpOnly` (default), `SameSite=lax` (mitiga CSRF), `Secure` configurável via `SESSION_HTTPS_ONLY`.
- Não há token CSRF explícito nos formulários — aceitável para uso interno com `SameSite=lax`; reavaliar se o app for exposto além da rede interna.
