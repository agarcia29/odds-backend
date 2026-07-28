def _covers_line(value: float, line: float, over: bool) -> bool:
    return value > line if over else value < line


def hit_rate_from_values(values: list, line: float, over: bool) -> dict | None:
    """
    Calcula cuantas veces (de una lista de valores historicos) se hubiera
    cumplido la linea. Devuelve None si hay menos de 2 partidos (no es un
    porcentaje confiable de mostrar).
    """
    if len(values) < 2:
        return None
    hits = sum(1 for v in values if _covers_line(v, line, over))
    total = len(values)
    return {"hits": hits, "total": total, "pct": round(hits / total * 100)}


def build_player_insights(entries: list, line: float, over: bool, opponent_id, last_n: int) -> dict:
    """
    Recibe una lista NORMALIZADA de partidos (mas reciente primero), cada
    uno como {"value":..., "opponent_id":..., "is_home":...}. Independiente
    de si vienen de balldontlie, MLB Stats API, etc. -- esa conversion la
    hace cada cliente de datos por separado.

    Arma los recortes:
      - overall: ultimos N partidos
      - vs_opponent: enfrentamientos recientes contra ese rival puntual
    """
    result = {}

    recent_values = [e["value"] for e in entries[:last_n]]
    overall = hit_rate_from_values(recent_values, line, over)
    if overall:
        result["overall"] = {**overall, "label": f"Ultimos {overall['total']} partidos"}

    if opponent_id is not None:
        vs_opp_values = [e["value"] for e in entries if e.get("opponent_id") == opponent_id][:last_n]
        vs_opp = hit_rate_from_values(vs_opp_values, line, over)
        if vs_opp:
            result["vs_opponent"] = {**vs_opp, "label": f"Ultimos {vs_opp['total']} vs este rival"}

    return result
