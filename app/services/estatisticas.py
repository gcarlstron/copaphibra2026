"""Painéis de BI no Grafana (public dashboards) — referência + lookup.

São *public dashboards* do Grafana Cloud (públicos por natureza, não são segredo),
então as URLs ficam no código. O Cloud free serve esses painéis com
``Content-Security-Policy: frame-ancestors 'none'``, ou seja **não** permite embed
via ``<iframe>`` — por isso o app apenas **linka** (botão + nova aba), em vez de
embedar. Quando o Grafana for self-hosted (com ``allow_embedding``), trocamos os
links por iframes e um dashboard único com variável ``$jogador``.

Mapa por **nome** do jogador (o `Usuario.nome` casa exatamente com estas chaves).
"""

from __future__ import annotations

_BASE = "https://fearlesszinnia2484.grafana.net/public-dashboards"

# Quadro geral (classificação / comparativo entre todos).
PAINEL_GERAL_URL = f"{_BASE}/344dbff777584f80bac1f0f8d0387823"

# Painel individual de cada jogador.
_PAINEIS_JOGADORES: dict[str, str] = {
    "Bernardo": f"{_BASE}/f660e6fdfd534f6fa19ebe0ca4845010",
    "Fernando": f"{_BASE}/0834d987bbb84365a0704b1a90625868",
    "Gabriel": f"{_BASE}/d038ebe6331d4fb6a930cac944dbd6ea",
    "Gustavo": f"{_BASE}/990cfcc3cb7340e497f2456a41c89e02",
    "Marcio": f"{_BASE}/3c02e44782864b80821d071d7fc4a787",
    "Marques": f"{_BASE}/144b9f58db804fe78d37d3646312a333",
    "Renan": f"{_BASE}/9dbecb8b4fea4c16a310ab8d7494b7e1",
    "Ricardo": f"{_BASE}/3e58eb58749b4a15be36914fd85cb2bb",
    "Soares": f"{_BASE}/8cd20cf725644ce6aba68359b4f562b4",
    "Thiago": f"{_BASE}/7894eef30973463c97f26e35fdba13e3",
}


def painel_do_jogador(nome: str) -> str | None:
    """URL do painel individual do jogador (por nome), ou None se não houver."""
    return _PAINEIS_JOGADORES.get(nome)
