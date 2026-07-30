def _covers_line(value: float, line: float, over: bool) -> bool:
    return value > line if over else value < line


def hit_rate_from_bools(bools: list) -> dict | None:
    """
    A partir de una lista de True/False (cada uno = "esto se cumplio en
    ese partido"), calcula hits/total/pct. None si hay menos de 2 datos
    (no es un porcentaje confiable de mostrar).
    """
    if len(bools) < 2:
        return None
    hits = sum(1 for b in bools if b)
    total = len(bools)
    return {"hits": hits, "total": total, "pct": round(hits / total * 100)}


def _build_insight_lines(entries: list, hit_fn, opponent_id, label_suffix: str = "") -> list:
    """
    entries: lista de partidos/registros (mas reciente primero).
    hit_fn: funcion que recibe una entry y devuelve True/False.
    Arma hasta 3 lineas: ultimos 5, ultimos 10, vs rival puntual.
    label_suffix: texto opcional para distinguir de que equipo/jugador es
    (util cuando se combinan 2 perspectivas, ej en el mercado de totales).
    """
    lines = []

    r5 = hit_rate_from_bools([hit_fn(e) for e in entries[:5]])
    if r5:
        lines.append({**r5, "label": f"Ultimos 5 partidos{label_suffix}"})

    r10 = hit_rate_from_bools([hit_fn(e) for e in entries[:10]])
    if r10:
        lines.append({**r10, "label": f"Ultimos 10 partidos{label_suffix}"})

    if opponent_id is not None:
        vs_entries = [e for e in entries if e.get("opponent_id") == opponent_id][:10]
        rvs = hit_rate_from_bools([hit_fn(e) for e in vs_entries])
        if rvs:
            lines.append({**rvs, "label": f"Ultimos {rvs['total']} vs este rival{label_suffix}"})

    return lines


def build_player_insights(entries: list, line: float, over: bool, opponent_id) -> list:
    """Mercados de jugador (props): entries traen {"value":...}."""
    return _build_insight_lines(entries, lambda e: _covers_line(e["value"], line, over), opponent_id)


def build_team_h2h_insights(games: list, opponent_id) -> list:
    """Mercado ganador (h2h): hit = el equipo gano ese partido."""
    return _build_insight_lines(games, lambda g: g["team_score"] > g["opp_score"], opponent_id)


def build_team_spread_insights(games: list, point: float, opponent_id) -> list:
    """
    Mercado handicap: hit = el equipo cubrio la linea. Formula estandar:
    cubre si (marcador_equipo - marcador_rival) > -point (funciona para
    favoritos con point negativo y para no-favoritos con point positivo).
    """
    return _build_insight_lines(games, lambda g: (g["team_score"] - g["opp_score"]) > -point, opponent_id)


def build_team_total_insights(games: list, point: float, over: bool, opponent_id, label_suffix: str = "") -> list:
    """Mercado totales: hit = el total combinado de ESE partido paso la linea."""
    return _build_insight_lines(
        games, lambda g: _covers_line(g["team_score"] + g["opp_score"], point, over), opponent_id, label_suffix
    )


def best_pct(insight_lines: list) -> float | None:
    """El % mas alto entre todas las lineas calculadas (se usa tanto para
    el filtro de % minimo como para decidir si se marca como VALOR)."""
    if not insight_lines:
        return None
    return max(line["pct"] for line in insight_lines)
