from datetime import datetime


def _covers_line(value: float, line: float, over: bool) -> bool:
    return value > line if over else value < line


def hit_rate_from_values(values: list[float], line: float, over: bool) -> dict | None:
    """
    Calcula cuantas veces (de una lista de valores historicos) se hubiera
    cumplido la linea. Devuelve None si no hay suficientes datos (menos
    de 2 partidos no es un porcentaje confiable de mostrar).
    """
    if len(values) < 2:
        return None
    hits = sum(1 for v in values if _covers_line(v, line, over))
    total = len(values)
    return {"hits": hits, "total": total, "pct": round(hits / total * 100)}


def build_player_insights(stat_logs: list[dict], stat_field: str, line: float, over: bool, opponent_team_id: int | None, last_n: int) -> dict:
    """
    A partir del log de partidos de un jugador (mas reciente primero),
    arma los 3 recortes que se ven en la captura de referencia:
      - overall: ultimos N partidos
      - vs_opponent: todos los enfrentamientos recientes contra ese rival
      - home: ultimos partidos de local (si el dato de local/visitante esta disponible)
    """
    result = {}

    recent_values = [s.get(stat_field) for s in stat_logs[:last_n] if s.get(stat_field) is not None]
    overall = hit_rate_from_values(recent_values, line, over)
    if overall:
        result["overall"] = {**overall, "label": f"Ultimos {overall['total']} partidos"}

    if opponent_team_id is not None:
        vs_opp_values = [
            s.get(stat_field)
            for s in stat_logs
            if s.get(stat_field) is not None
            and (
                (s.get("game") or {}).get("home_team_id") == opponent_team_id
                or (s.get("game") or {}).get("visitor_team_id") == opponent_team_id
            )
        ][:last_n]
        vs_opp = hit_rate_from_values(vs_opp_values, line, over)
        if vs_opp:
            result["vs_opponent"] = {**vs_opp, "label": f"Ultimos {vs_opp['total']} vs este rival"}

    return result


def build_team_total_insights(games: list[dict], team_id: int, line: float, over: bool, opponent_team_id: int | None, last_n: int) -> dict:
    """
    Igual que build_player_insights pero para el total de carreras/puntos
    anotados por UN equipo (no el total combinado del partido).
    """
    result = {}

    def team_score(game: dict) -> float | None:
        if game.get("home_team_id") == team_id:
            return game.get("home_team_score")
        if game.get("visitor_team_id") == team_id:
            return game.get("visitor_team_score")
        return None

    recent_values = [v for v in (team_score(g) for g in games[:last_n]) if v is not None]
    overall = hit_rate_from_values(recent_values, line, over)
    if overall:
        result["overall"] = {**overall, "label": f"Ultimos {overall['total']} partidos"}

    if opponent_team_id is not None:
        vs_opp_games = [
            g for g in games
            if g.get("home_team_id") == opponent_team_id or g.get("visitor_team_id") == opponent_team_id
        ][:last_n]
        vs_opp_values = [v for v in (team_score(g) for g in vs_opp_games) if v is not None]
        vs_opp = hit_rate_from_values(vs_opp_values, line, over)
        if vs_opp:
            result["vs_opponent"] = {**vs_opp, "label": f"Ultimos {vs_opp['total']} vs este rival"}

    return result
