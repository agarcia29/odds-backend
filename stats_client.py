import httpx

from config import BALLDONTLIE_API_KEY, BALLDONTLIE_BASE


async def bdl_get(path: str, params: dict) -> dict | None:
    """
    Llama a balldontlie. Devuelve None (en vez de lanzar excepcion) si
    algo falla, porque las estadisticas son un "extra" que enriquece la
    respuesta de /api/odds -- si fallan, el resto de la app debe seguir
    funcionando normal, solo sin el dato de insights.
    """
    if not BALLDONTLIE_API_KEY:
        return None
    url = f"{BALLDONTLIE_BASE}{path}"
    headers = {"Authorization": BALLDONTLIE_API_KEY}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params, headers=headers)
        if resp.status_code != 200:
            return None
        return resp.json()
    except httpx.HTTPError:
        return None


async def bdl_get_debug(path: str, params: dict) -> dict:
    """
    Igual que bdl_get pero SIN tragarse el error -- devuelve status_code
    y el cuerpo crudo de la respuesta para poder diagnosticar por que
    fallo una llamada (403 de plan, 404 de endpoint, 400 de parametros, etc).
    Solo se usa desde /api/debug/balldontlie.
    """
    if not BALLDONTLIE_API_KEY:
        return {"error": "BALLDONTLIE_API_KEY no configurada"}
    url = f"{BALLDONTLIE_BASE}{path}"
    headers = {"Authorization": BALLDONTLIE_API_KEY}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params, headers=headers)
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        return {"status_code": resp.status_code, "body": body}
    except httpx.HTTPError as e:
        return {"error": str(e)}


def _normalize(name: str) -> str:
    return name.strip().lower()


async def find_team_id(sport_prefix: str, team_name: str) -> int | None:
    """
    Busca el id de equipo en balldontlie por nombre. The Odds API manda
    nombres completos (ej "New York Mets"), balldontlie normalmente trae
    'full_name' o 'name' -- probamos match flexible por si acaso.
    """
    data = await bdl_get(f"/{sport_prefix}/v1/teams", {"per_page": 100})
    if not data or "data" not in data:
        return None

    target = _normalize(team_name)
    for team in data["data"]:
        candidates = [team.get("full_name", ""), team.get("name", ""), team.get("display_name", "")]
        if any(_normalize(c) == target for c in candidates if c):
            return team.get("id")

    # match parcial (ej "Mets" dentro de "New York Mets") como respaldo
    for team in data["data"]:
        candidates = [team.get("full_name", ""), team.get("name", "")]
        if any(target in _normalize(c) or _normalize(c) in target for c in candidates if c):
            return team.get("id")

    return None


async def find_player_id(sport_prefix: str, player_description: str, team_id: int | None = None) -> dict | None:
    """
    Busca el jugador y devuelve {"id":..., "team_id":...}. The Odds API a
    veces manda el nombre abreviado (ej "C. Scott" en vez de "Christian
    Scott"), asi que buscamos por el apellido (ultima palabra) y, si hay
    varios resultados, preferimos el que juegue en el equipo esperado
    (team_id) para desambiguar.
    """
    last_name = player_description.strip().split(" ")[-1]
    data = await bdl_get(f"/{sport_prefix}/v1/players", {"search": last_name, "per_page": 25})
    if not data or not data.get("data"):
        return None

    candidates = data["data"]
    if team_id is not None:
        for p in candidates:
            p_team = p.get("team") or {}
            if p_team.get("id") == team_id:
                return {"id": p.get("id"), "team_id": p_team.get("id")}

    # sin team_id o sin match de equipo, nos quedamos con el primer resultado
    first = candidates[0]
    first_team = (first.get("team") or {}).get("id")
    return {"id": first.get("id"), "team_id": first_team}


async def get_team_recent_games(sport_prefix: str, team_id: int, limit_seasons: list[int]) -> list[dict]:
    """
    Trae partidos recientes de un equipo (ya jugados, con marcador),
    mas nuevos primero. limit_seasons son las temporadas a incluir
    (normalmente la actual, y la anterior por si hay pocos partidos jugados).
    """
    data = await bdl_get(
        f"/{sport_prefix}/v1/games",
        {"team_ids[]": team_id, "seasons[]": limit_seasons, "per_page": 100},
    )
    if not data or not data.get("data"):
        return []

    games = [g for g in data["data"] if g.get("status") in ("Final", "final", "Completed") or g.get("home_team_score")]
    games.sort(key=lambda g: g.get("date", ""), reverse=True)
    return games


async def get_player_recent_stats(sport_prefix: str, player_id: int, limit_seasons: list[int]) -> list[dict]:
    """
    Trae el log de estadisticas partido-por-partido de un jugador,
    mas reciente primero.
    """
    data = await bdl_get(
        f"/{sport_prefix}/v1/stats",
        {"player_ids[]": player_id, "seasons[]": limit_seasons, "per_page": 100},
    )
    if not data or not data.get("data"):
        return []

    stats = data["data"]
    stats.sort(key=lambda s: (s.get("game") or {}).get("date", ""), reverse=True)
    return stats
