import httpx

MLB_STATS_BASE = "https://statsapi.mlb.com/api/v1"

# Nota de uso: esta API es oficial de MLB, publica, sin api key, gratis para
# uso individual/no-comercial. Uso comercial o de volumen masivo requeriria
# autorizacion de MLB Advanced Media -- para un prototipo/app personal esto
# aplica sin problema, pero si el dia de manana la app se vuelve un producto
# comercial grande, vale la pena revisar los terminos de nuevo.


async def mlb_get(path: str, params: dict) -> dict | None:
    """
    Llama a la MLB Stats API. Devuelve None si algo falla -- las
    estadisticas son un "extra" que enriquece /api/odds, nunca deben
    tumbar la respuesta principal.
    """
    url = f"{MLB_STATS_BASE}{path}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params)
        if resp.status_code != 200:
            return None
        return resp.json()
    except httpx.HTTPError:
        return None


def _normalize(name: str) -> str:
    return name.strip().lower()


async def find_mlb_team_id(team_name: str) -> int | None:
    data = await mlb_get("/teams", {"sportId": 1})
    if not data or not data.get("teams"):
        return None

    target = _normalize(team_name)
    for team in data["teams"]:
        candidates = [team.get("name", ""), team.get("teamName", "")]
        if any(_normalize(c) == target for c in candidates if c):
            return team.get("id")

    for team in data["teams"]:
        candidates = [team.get("name", ""), team.get("teamName", "")]
        if any(target in _normalize(c) or _normalize(c) in target for c in candidates if c):
            return team.get("id")

    return None


async def find_mlb_player_id(team_id: int, player_description: str) -> int | None:
    """
    Busca al jugador DENTRO del roster del equipo que ya sabemos que
    participa en el partido (mucho mas confiable que una busqueda global
    por nombre, que puede traer jugadores retirados o de otro equipo con
    el mismo apellido).
    """
    data = await mlb_get(f"/teams/{team_id}/roster", {"rosterType": "fullSeason"})
    if not data or not data.get("roster"):
        return None

    last_name = _normalize(player_description.split(" ")[-1])
    for entry in data["roster"]:
        person = entry.get("person", {})
        full_name = _normalize(person.get("fullName", ""))
        if last_name and last_name in full_name.split(" "):
            return person.get("id")

    return None


async def get_player_game_log(player_id: int, group: str, seasons: list[int], stat_field: str) -> list[dict]:
    """
    Trae el log partido-por-partido de un jugador para un grupo de stats
    ("hitting" o "pitching") y devuelve una lista NORMALIZADA (mas
    reciente primero) con: value, opponent_id, is_home. Junta varias
    temporadas si hace falta (ej. inicio de temporada con pocos partidos).
    """
    entries = []
    for season in seasons:
        data = await mlb_get(
            f"/people/{player_id}/stats",
            {"stats": "gameLog", "group": group, "season": season},
        )
        if not data or not data.get("stats"):
            continue
        for stat_block in data["stats"]:
            for split in stat_block.get("splits", []):
                value = (split.get("stat") or {}).get(stat_field)
                if value is None:
                    continue
                entries.append(
                    {
                        "value": value,
                        "opponent_id": (split.get("opponent") or {}).get("id"),
                        "is_home": split.get("isHome"),
                        "date": split.get("date", ""),
                    }
                )

    entries.sort(key=lambda e: e["date"], reverse=True)
    return entries
