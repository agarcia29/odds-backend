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


def build_player_insights(entries: list, line: float, over: bool, opponent_id, last_n_vs_opponent: int = 10) -> dict:
    """
    Recibe una lista NORMALIZADA de partidos (mas reciente primero), cada
    uno como {"value":..., "opponent_id":..., "is_home":...}. Independiente
    de si vienen de balldontlie, MLB Stats API, etc. -- esa conversion la
    hace cada cliente de datos por separado.

    Arma 3 recortes fijos:
      - last5: ultimos 5 partidos
      - last10: ultimos 10 partidos
      - vs_opponent: enfrentamientos recientes contra ese rival puntual
    """
    result = {}

    last5 = hit_rate_from_values([e["value"] for e in entries[:5]], line, over)
    if last5:
        result["last5"] = {**last5, "label": "Ultimos 5 partidos"}

    last10 = hit_rate_from_values([e["value"] for e in entries[:10]], line, over)
    if last10:
        result["last10"] = {**last10, "label": "Ultimos 10 partidos"}

    if opponent_id is not None:
        vs_opp_values = [e["value"] for e in entries if e.get("opponent_id") == opponent_id][:last_n_vs_opponent]
        vs_opp = hit_rate_from_values(vs_opp_values, line, over)
        if vs_opp:
            result["vs_opponent"] = {**vs_opp, "label": f"Ultimos {vs_opp['total']} vs este rival"}

    return result


def best_pct(insights: dict) -> float | None:
    """
    Devuelve el % mas representativo para aplicar el filtro de "% minimo
    de acierto" -- usamos last10 si existe (mas muestra), si no last5.
    vs_opponent no se usa para el filtro principal porque suele tener
    muestra chica (a veces 2-3 partidos) y no queremos ocultar algo solo
    por ese numero mas ruidoso.
    """
    if "last10" in insights:
        return insights["last10"]["pct"]
    if "last5" in insights:
        return insights["last5"]["pct"]
    return None
