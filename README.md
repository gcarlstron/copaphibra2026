# Copa Phibra 2026

Bolão da Copa do Mundo 2026 para uso interno.

## Estado Atual

O andamento atual, decisões já tomadas e próximos passos estão registrados em [HANDOFF.md](HANDOFF.md).

## Como rodar (desenvolvimento)

```bash
pip install -r requirements.txt
python -m alembic upgrade head
python scripts/criar_admin.py          # cria admin/admin123 para entrar
python scripts/importar_planilha.py    # (opcional) carrega a planilha
uvicorn app.main:app --reload
```

Acesse http://127.0.0.1:8000 e entre com `admin` / `admin123`.

## Deploy interno

Para subir em produção (variáveis de ambiente, `SECRET_KEY`, HTTPS, checklist),
ver **[DEPLOY.md](DEPLOY.md)**. Em produção o app exige `SECRET_KEY` definido e
`DEBUG=0`. Configure via `.env` (modelo em [`.env.example`](.env.example)) e rode:

```bash
uvicorn app.main:app --env-file .env --host 0.0.0.0 --port 8000
```

## Variáveis de ambiente

| Variável | Padrão | Descrição |
|---|---|---|
| `SECRET_KEY` | `dev-secret-change-me` | Obrigatória em produção (app recusa subir com o padrão e `DEBUG=0`). |
| `DEBUG` | `0` | `1` em desenvolvimento. |
| `DATABASE_URL` | `sqlite:///./copa_phibra.db` | Pronto para PostgreSQL. |
| `SESSION_HTTPS_ONLY` | `0` | `1` marca o cookie de sessão como `Secure` (atrás de HTTPS). |

## Testes

```bash
python -m pytest -q
```

## Estrutura

- `app/` — base FastAPI, banco, models, services, routers e templates
- `migrations/` — histórico do Alembic
- `scripts/` — `criar_admin.py` e `importar_planilha.py`
- `tests/` — testes automatizados (pontuação, prazo, ranking, palpites, dashboard, admin, importação)
