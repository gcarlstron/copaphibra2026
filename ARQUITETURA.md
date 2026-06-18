# Copa Phibra 2026 — Sistema de Bolão

Documento de arquitetura. Define **como o sistema vai funcionar** antes de escrever código.
Baseado na planilha `COPA PHIBRA 2026 OFICIAL ATÉ A FINAL SEGUNDA FASE.xlsx`.

> Status: **proposta para revisão**. Nada de código ainda — primeiro alinhamos este documento.

---

## 1. Visão geral

Sistema web para um **bolão da Copa do Mundo 2026**. Cada participante (Phibriano)
faz seus palpites de placar para cada jogo. Quando o resultado oficial sai, o sistema
calcula automaticamente os pontos de cada um (substituindo as planilhas manuais de hoje)
e mantém a classificação atualizada com os critérios de desempate.

**Princípios:**
- Interface **simples** — pouca coisa na tela, foco em "ver jogos" e "palpitar".
- **Dados entram manualmente** numa primeira fase (jogos, resultados, palpites).
- Cada usuário **só edita o próprio palpite**; só o admin lança o **resultado oficial**.
- Palpite tem **prazo**: trava no início da partida ("até quando pode colocar").

---

## 2. Decisões de stack

| Camada | Escolha | Por quê |
|--------|---------|---------|
| Linguagem/Backend | **Python + FastAPI** | Definido com o time. Rápido, tipado, fácil de manter. |
| Banco de dados | **SQLite** (início) → PostgreSQL (se crescer) | Escala pequena (~13 jogadores). Zero infra para começar; migração simples depois. |
| ORM / Migrations | **SQLAlchemy** + **Alembic** | Modelo de dados versionado. |
| Frontend | **Jinja2 (server-side) + HTMX** + CSS simples | Telas renderizadas no servidor, com interatividade pontual (salvar palpite sem recarregar). Sem build de JS, mantém simples. |
| Autenticação | **Sessão por cookie + senha com hash (bcrypt/passlib)** | Login com usuário e senha por jogador. |
| Servidor | **Uvicorn** | Padrão FastAPI. |

> Alternativa de frontend, caso queiram algo mais "app": trocar Jinja+HTMX por um SPA
> (React/Vue) consumindo a API REST do FastAPI. A API já seria desenhada para suportar isso.

---

## 3. Regras de negócio (extraídas da planilha)

### 3.1 Pontuação por jogo

Comparando o **palpite** (placar mandante × visitante) com o **resultado oficial**:

| Pontos | Critério |
|:------:|----------|
| **9** | Acertou o vencedor (ou o empate) **e o placar exato**. |
| **6** | Acertou o vencedor **e o nº de gols do vencedor** (placar não exato); **ou** acertou que foi **empate** mas com nº de gols diferente. |
| **4** | Acertou o vencedor **e o nº de gols do perdedor** (mas não os gols do vencedor). |
| **3** | Acertou **só o vencedor** — ambos os placares errados. |
| **0** | **Errou o vencedor**, ou errou um jogo que terminou empate. |

**Algoritmo de cálculo** (`services/scoring.py`):

```
def calcular_pontos(palpite_casa, palpite_visit, oficial_casa, oficial_visit) -> int:
    res_palpite = sinal(palpite_casa - palpite_visit)   # 1=casa, -1=visit, 0=empate
    res_oficial = sinal(oficial_casa - oficial_visit)

    if res_palpite != res_oficial:
        return 0                                          # errou o vencedor / empate

    if palpite_casa == oficial_casa and palpite_visit == oficial_visit:
        return 9                                          # placar exato

    if res_oficial == 0:                                  # empate, placar diferente
        return 6

    # acertou o vencedor, placar não exato — descobrir gols do vencedor/perdedor
    if res_oficial == 1:   # mandante venceu
        gols_venc_p, gols_perd_p = palpite_casa,  palpite_visit
        gols_venc_o, gols_perd_o = oficial_casa,  oficial_visit
    else:                  # visitante venceu
        gols_venc_p, gols_perd_p = palpite_visit, palpite_casa
        gols_venc_o, gols_perd_o = oficial_visit, oficial_casa

    if gols_venc_p == gols_venc_o:
        return 6
    if gols_perd_p == gols_perd_o:
        return 4
    return 3
```

*(Validado contra os pontos já preenchidos na aba de um jogador na planilha.)*

### 3.2 Classificação e desempate

Ranking ordenado por **total de pontos** (desc). Em caso de empate, aplica-se, **nesta ordem**:

1. Maior número de jogos com **9** pontos
2. Maior número de jogos com **6** pontos
3. Maior número de jogos com **4** pontos
4. Maior número de jogos com **3** pontos
5. **Sorteio** (decisão manual do admin)

Cada participante tem, então: `total`, `qtd_9`, `qtd_6`, `qtd_4`, `qtd_3`.

### 3.3 Prazo dos palpites — controle manual por rodada

Os palpites são organizados em **rodadas** (lotes de jogos), e quem controla quando
cada rodada abre e fecha é o **admin** — não é automático pelo horário do jogo.

**Rodadas da fase de grupos** (cada time joga 3 vezes; 24 jogos por rodada):
| Rodada | Jogos (linhas da planilha) | Descrição |
|--------|----------------------------|-----------|
| 1ª rodada | linhas 2–25 | 1º jogo de cada time |
| 2ª rodada | linhas 26–49 | 2º jogo de cada time |
| 3ª rodada | linhas 50–73 | 3º jogo de cada time |
| Mata-mata | seguintes | 16-avos, oitavas, etc. |

**Como o admin controla** (cada rodada tem):
- `aberta` (sim/não) — liga/desliga manualmente; e/ou
- `abertura` / `fechamento` (datas opcionais) — janela automática.

Uma rodada está **aberta para palpite** quando: `aberta = sim` **e**, se houver datas,
`abertura ≤ agora ≤ fechamento`.

Exemplo do que você descreveu:
- Hoje a **2ª rodada (linhas 26–49)** está aberta → pode palpitar.
- A **3ª rodada (linhas 50+)** está fechada → ainda não pode.
- Depois o admin abre a 3ª no **dia X** e fecha no **dia Y**.

**Regras derivadas:**
- Palpite só pode ser criado/editado enquanto a rodada está aberta. Fora disso, somente leitura.
- **Privacidade:** os palpites dos outros só ficam **visíveis depois que a rodada fecha**
  (antes disso, cada um vê só o próprio — evita cópia).

---

## 4. Modelo de dados

```
Usuario
  id            PK
  nome          (ex. "Gustavo")
  username      único (login)
  senha_hash
  is_admin      bool
  ativo         bool

Rodada
  id            PK
  nome          ("1ª Rodada", "2ª Rodada", "Oitavas", ...)
  ordem         int (ordenação)
  aberta        bool   (liga/desliga manual do admin)
  abertura      datetime (nullable — abre automaticamente a partir de)
  fechamento    datetime (nullable — fecha automaticamente em)
  -- aberta para palpite = aberta AND (sem datas OU abertura <= agora <= fechamento)

Jogo
  id            PK
  rodada_id     FK -> Rodada
  data_hora     datetime (kickoff — só para exibição/ordenação)
  time_casa     texto
  time_visitante texto
  gols_casa     int  (nullable — preenchido pelo admin no resultado)
  gols_visitante int (nullable)
  status        ("agendado" | "encerrado")

Palpite
  id            PK
  usuario_id    FK -> Usuario
  jogo_id       FK -> Jogo
  gols_casa     int
  gols_visitante int
  pontos        int  (calculado quando o resultado é lançado; cache)
  criado_em
  atualizado_em
  UNIQUE(usuario_id, jogo_id)   -- um palpite por jogo por pessoa
```

> `pontos` é um cache: recalculado sempre que o admin lança/edita o resultado do jogo.
> A classificação é derivada agregando os palpites (não precisa de tabela própria).

**Participantes (10 ativos, da planilha):** Bernardo, Thiago, Ricardo, Fernando,
Gustavo, Marcio, Gabriel, Renan, Soares, Marques.

---

## 5. Telas

### 5.1 Login
Usuário + senha. (Cadastro de usuários é feito pelo admin.)

### 5.2 Tela principal / Dashboard *(página inicial)*
- **Classificação geral**: posição, nome, pontos, e o detalhamento (qtd de 9/6/4/3).
- **Acompanhamento dos jogos**: últimos resultados oficiais e próximos jogos com horário.
- Destaque das **rodadas abertas para palpite** e até quando ficam abertas.

### 5.3 Meus Palpites
- Agrupado **por rodada**. Para cada rodada mostra o status (aberta / fechada / em breve).
  - Rodada **aberta**: campos editáveis de placar em cada jogo + botão salvar.
  - Rodada **fechada**: mostra o palpite, o resultado oficial e os pontos ganhos.
- Indicador claro ("Aberta até dd/mm hh:mm" / "Encerrada" / "Abre em dd/mm").

### 5.4 Detalhe do Jogo
- Placar oficial e a lista de **palpites de todos** + pontos
  (visível só **depois que a rodada fecha**).

### 5.5 Área Admin
- **Gerenciar rodadas**: criar rodada, atribuir jogos, e o **controle de prazo** —
  ligar/desligar `aberta` e definir as datas de `abertura`/`fechamento`.
  (Ex.: abrir a 3ª rodada no dia X e fechar no dia Y; deixar as futuras fechadas.)
- **Cadastrar/editar jogos** (data, hora, times, rodada).
- **Lançar resultado oficial** → dispara o recálculo de pontos de todos os palpites do jogo.
- **Gerenciar usuários** (criar, resetar senha, ativar/desativar).

---

## 6. API (rotas principais)

```
POST   /login                       autenticação
POST   /logout

GET    /                            dashboard (ranking + jogos)
GET    /palpites                    meus palpites (agrupados por rodada)
POST   /palpites/{jogo_id}          salvar/editar meu palpite (valida rodada aberta)
GET    /jogos/{id}                  detalhe do jogo (+ palpites se a rodada fechou)
GET    /ranking                     classificação (JSON, p/ futuro SPA)

-- Admin --
GET    /admin/rodadas
POST   /admin/rodadas               criar rodada
PUT    /admin/rodadas/{id}          editar rodada (aberta, abertura, fechamento)
GET    /admin/jogos
POST   /admin/jogos                 criar jogo
PUT    /admin/jogos/{id}            editar jogo
POST   /admin/jogos/{id}/resultado  lançar resultado -> recalcula pontos
GET    /admin/usuarios
POST   /admin/usuarios              criar usuário
```

Regras aplicadas no backend (não só na tela):
- Salvar palpite valida que a **rodada do jogo está aberta** e que o palpite é do próprio usuário.
- Lançar resultado e gerenciar rodadas é restrito a `is_admin`.

---

## 7. Estrutura de pastas

```
CopaPhibra/
├── ARQUITETURA.md            # este documento
├── README.md                 # como rodar
├── requirements.txt
├── app/
│   ├── main.py               # cria o app FastAPI, monta rotas
│   ├── config.py             # configurações (SECRET, banco, prazo-buffer)
│   ├── database.py           # engine + sessão SQLAlchemy
│   ├── models/               # Usuario, Jogo, Palpite
│   ├── schemas/              # Pydantic (validação de entrada/saída)
│   ├── routers/              # auth, dashboard, palpites, jogos, admin
│   ├── services/
│   │   ├── scoring.py        # cálculo de pontos (seção 3.1)
│   │   ├── ranking.py        # classificação + desempate (seção 3.2)
│   │   └── prazo.py          # regras de prazo/visibilidade (seção 3.3)
│   ├── templates/            # Jinja2 (login, dashboard, palpites, admin)
│   └── static/               # css, htmx
├── migrations/               # Alembic
├── scripts/
│   └── importar_planilha.py  # importa jogos + palpites da .xlsx (seed inicial)
└── tests/
    ├── test_scoring.py       # casos validados contra a planilha
    └── test_prazo.py
```

---

## 8. Importação inicial (evita redigitar)

A planilha já tem todos os jogos, vários resultados e palpites preenchidos.
O script `scripts/importar_planilha.py` vai:
1. Criar as **rodadas** e mapear os jogos pelas linhas da aba `OFICIAL`
   (1ª = 2–25, 2ª = 26–49, 3ª = 50–73, depois mata-mata).
2. Cadastrar os **jogos** e os **resultados** já conhecidos.
3. Ler cada aba de jogador (só os 10 ativos) → cadastrar os **palpites** existentes.
4. Criar os **usuários** (senha provisória, trocada no primeiro acesso).

Assim o sistema "nasce" já com o estado atual do bolão, e seguimos manualmente daqui pra frente.

---

## 9. Fora de escopo (por enquanto)

- Importação automática de resultados de uma API de futebol (hoje é manual, como pedido).
- Notificações/e-mail de "falta palpitar".
- App mobile nativo (a interface web é responsiva).

Esses itens podem virar uma fase 2.

---

## 10. Próximos passos

1. **Revisar e aprovar este documento.**
2. Scaffolding do projeto (FastAPI + SQLAlchemy + Alembic + templates).
3. Implementar `scoring.py` com testes contra a planilha.
4. Importador da planilha.
5. Telas (login → dashboard → meus palpites → admin).
6. Deploy interno.
```
