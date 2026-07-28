from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from cache import events_cache, leagues_cache, make_key, odds_cache
from config import (
    BALLDONTLIE_API_KEY,
    BDL_SPORT_PREFIX,
    DEFAULT_MARKETS,
    DEFAULT_REGIONS,
    FEATURED_MARKETS,
    INSIGHTS_LAST_N_GAMES,
    MARKET_STAT_FIELDS,
    MATCH_MARKETS_BY_SPORT,
    PLAYER_MARKETS_BY_SPORT,
    PLAYER_PROPS_REGIONS,
    REGIONS_BY_SPORT,
    SPORT_GROUPS,
)
from odds_client import odds_api_get
from stats_client import bdl_get, bdl_get_debug, find_player_id, find_team_id, get_player_recent_stats
from insights import build_player_insights

# Colombia no tiene horario de verano, siempre UTC-5. Se usa para decidir
# que partido cuenta como "de hoy" al filtrar eventos.
COLOMBIA_TZ = timezone(timedelta(hours=-5))


def _is_today_in_colombia(commence_time_iso: str) -> bool:
    event_dt = datetime.fromisoformat(commence_time_iso.replace("Z", "+00:00"))
    event_date_co = event_dt.astimezone(COLOMBIA_TZ).date()
    today_co = datetime.now(COLOMBIA_TZ).date()
    return event_date_co == today_co


app = FastAPI(title="Odds Filter API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/debug/balldontlie")
async def debug_balldontlie(
    sport: str = Query(..., description="beisbol | basquetbol"),
    team: Optional[str] = Query(None, description="nombre de equipo a probar, ej 'New York Mets'"),
    player: Optional[str] = Query(None, description="nombre/apellido de jugador a probar, ej 'Scott'"),
):
    """
    Endpoint de diagnostico (no lo usa la app, es para ti/nosotros).
    Te dice: si la key esta configurada, si balldontlie responde, y te
    muestra el JSON crudo para poder confirmar los nombres de campo reales.
    Ejemplo: /api/debug/balldontlie?sport=beisbol&team=New York Mets&player=Scott
    """
    prefix = BDL_SPORT_PREFIX.get(sport.lower())
    if not prefix:
        raise HTTPException(status_code=400, detail=f"Deporte no soportado para stats todavia: {sport}")

    result = {"key_configured": bool(BALLDONTLIE_API_KEY), "sport_prefix": prefix}

    teams_data = await bdl_get(f"/{prefix}/v1/teams", {"per_page": 3})
    result["teams_call_worked"] = teams_data is not None
    result["teams_sample"] = teams_data

    team_id_found = None
    if team:
        team_id_found = await find_team_id(prefix, team)
        result["team_id_found"] = team_id_found

    if player:
        # Busqueda cruda (todos los candidatos) para poder ver que trae balldontlie
        raw_search = await bdl_get(f"/{prefix}/v1/players", {"search": player.split(" ")[-1], "per_page": 25})
        result["player_search_candidates"] = [
            {"id": c.get("id"), "name": f"{c.get('first_name')} {c.get('last_name')}", "team": c.get("team")}
            for c in (raw_search or {}).get("data", [])
        ]

        p = await find_player_id(prefix, player, team_id_found)
        result["player_found"] = p
        if p and p.get("id"):
            seasons = [datetime.now().year, datetime.now().year - 1]
            debug_stats = await bdl_get_debug(
                f"/{prefix}/v1/stats", {"player_ids[]": p["id"], "seasons[]": seasons, "per_page": 5}
            )
            result["raw_stats_response_debug"] = debug_stats
            stats = await get_player_recent_stats(prefix, p["id"], seasons)
            result["stats_sample_first_game"] = stats[0] if stats else None
            result["stats_sample_count"] = len(stats)

    return result


@app.get("/api/sports")
async def get_sports():
    """
    Devuelve los 4 deportes que soporta la app. Esto es fijo (no depende
    de la API externa) para que el primer filtro (obligatorio) sea simple.
    """
    return [{"key": key, "label": key.capitalize()} for key in SPORT_GROUPS.keys()]


@app.get("/api/leagues")
async def get_leagues(sport: str = Query(..., description="futbol | tenis | beisbol | basquetbol")):
    """
    Devuelve las ligas (sport keys de The Odds API) que pertenecen al
    deporte elegido. Ej: sport=futbol -> soccer_epl, soccer_spain_la_liga, etc.
    """
    group = SPORT_GROUPS.get(sport.lower())
    if not group:
        raise HTTPException(status_code=400, detail=f"Deporte invalido: {sport}")

    cache_key = make_key("leagues", sport)
    if cache_key in leagues_cache:
        return leagues_cache[cache_key]

    all_sports, _ = await odds_api_get("/sports", {})
    leagues = [
        {"key": s["key"], "title": s["title"], "active": s.get("active", True)}
        for s in all_sports
        if s.get("group") == group
    ]
    leagues_cache[cache_key] = leagues
    return leagues


@app.get("/api/extra-markets")
async def get_extra_markets(sport: str = Query(..., description="futbol | tenis | beisbol | basquetbol")):
    """
    Catalogo estatico de mercados "adicionales" soportados por deporte,
    separados en dos categorias:
      - player_markets: props de jugador (ej. puntos, goles, hits)
      - match_markets: del partido pero fuera de h2h/spreads/totals (ej. BTTS)
    Todos requieren event_id (no se pueden pedir en bloque). No llama a
    The Odds API (no consume cuota); es solo para poblar los checkboxes.
    """
    sport_key = sport.lower()
    if sport_key not in SPORT_GROUPS:
        raise HTTPException(status_code=400, detail=f"Deporte invalido: {sport}")
    return {
        "player_markets": PLAYER_MARKETS_BY_SPORT.get(sport_key, []),
        "match_markets": MATCH_MARKETS_BY_SPORT.get(sport_key, []),
    }


@app.get("/api/events")
async def get_events(
    sport: str = Query(..., description="futbol | tenis | beisbol | basquetbol"),
    league: Optional[str] = Query(None, description="sport key especifico, ej soccer_epl"),
    only_today: bool = Query(True, description="si es true (default), solo devuelve partidos de hoy en hora Colombia"),
):
    """
    Devuelve los eventos (partidos) disponibles. Si no se pasa 'league',
    junta los eventos de todas las ligas del deporte elegido.
    Por defecto solo devuelve los partidos del dia de hoy (hora Colombia,
    UTC-5); manda only_today=false para ver todo el calendario disponible.
    Este endpoint no consume cuota de la API (es gratis).
    """
    leagues_to_query = [league] if league else [l["key"] for l in await get_leagues(sport)]

    all_events = []
    for league_key in leagues_to_query:
        cache_key = make_key("events", league_key)
        if cache_key in events_cache:
            events = events_cache[cache_key]
        else:
            try:
                events, _ = await odds_api_get(f"/sports/{league_key}/events", {})
            except HTTPException:
                # Si una liga puntual falla (ej. fuera de temporada), seguimos con las demas
                continue
            events_cache[cache_key] = events

        for e in events:
            if only_today and not _is_today_in_colombia(e["commence_time"]):
                continue
            all_events.append(
                {
                    "id": e["id"],
                    "league": league_key,
                    "home_team": e.get("home_team"),
                    "away_team": e.get("away_team"),
                    "commence_time": e.get("commence_time"),
                }
            )

    return all_events


# Un resultado se considera "valor" si la mejor cuota disponible supera el
# promedio del mercado por al menos este porcentaje.
VALUE_THRESHOLD_PCT = 3.0


def _aggregate_and_filter_outcomes(odds_response: list, min_odds: float, max_odds: float) -> list:
    """
    Recorre la respuesta cruda de The Odds API (que trae una casa de apuestas
    por bloque, cada una con sus propios outcomes) y la colapsa en un solo
    resultado por (mercado, nombre, jugador, punto), quedandose con la cuota
    MAS ALTA entre todas las casas que la ofrecen. No exponemos el nombre de
    la casa porque ninguna es colombiana; solo nos interesa el numero.

    Para mercados de jugador, The Odds API manda el nombre del jugador en
    el campo "description" (name sigue siendo "Over"/"Under"), por eso
    se incluye en la clave de deduplicacion y se expone como "player".

    Tambien calculamos el promedio de esa cuota entre casas, para poder
    marcar cuando la mejor cuota esta claramente por encima del promedio
    (senal de "valor").
    """
    filtered_events = []
    for event in odds_response:
        # market_key -> (name, description, point) -> lista de precios de todas las casas
        markets_acc: dict[str, dict[tuple, list]] = {}

        for bookmaker in event.get("bookmakers", []):
            for market in bookmaker.get("markets", []):
                market_key = market["key"]
                markets_acc.setdefault(market_key, {})
                for outcome in market.get("outcomes", []):
                    price = outcome.get("price")
                    if price is None:
                        continue
                    dedup_key = (outcome.get("name"), outcome.get("description"), outcome.get("point"))
                    markets_acc[market_key].setdefault(dedup_key, []).append(price)

        result_markets = []
        for market_key, outcomes_dict in markets_acc.items():
            matching_outcomes = []
            for (name, description, point), prices in outcomes_dict.items():
                best_price = max(prices)
                if not (min_odds <= best_price <= max_odds):
                    continue
                avg_price = sum(prices) / len(prices)
                value_pct = ((best_price - avg_price) / avg_price * 100) if avg_price else 0.0
                outcome_data = {
                    "name": name,
                    "price": round(best_price, 2),
                    "avg_price": round(avg_price, 2),
                    "bookmaker_count": len(prices),
                    "is_value": value_pct >= VALUE_THRESHOLD_PCT,
                }
                if point is not None:
                    outcome_data["point"] = point
                if description is not None:
                    outcome_data["player"] = description
                matching_outcomes.append(outcome_data)

            if matching_outcomes:
                matching_outcomes.sort(key=lambda o: o["price"])
                result_markets.append({"key": market_key, "outcomes": matching_outcomes})

        if result_markets:
            filtered_events.append(
                {
                    "id": event["id"],
                    "sport_key": event.get("sport_key"),
                    "home_team": event.get("home_team"),
                    "away_team": event.get("away_team"),
                    "commence_time": event.get("commence_time"),
                    "markets": result_markets,
                }
            )
    return filtered_events


async def _enrich_events_with_player_insights(sport_key: str, events: list) -> None:
    """
    Le agrega a cada outcome de mercado de jugador un campo "insights" con
    el % de acierto historico (usa balldontlie). Modifica 'events' in-place.
    Si algo falla (sin API key, jugador no encontrado, etc.) simplemente
    no agrega insights a ese outcome -- nunca rompe la respuesta principal.
    """
    prefix = BDL_SPORT_PREFIX.get(sport_key)
    stat_fields = MARKET_STAT_FIELDS.get(sport_key, {})
    if not prefix or not stat_fields:
        return

    current_year = datetime.now().year
    seasons = [current_year, current_year - 1]

    for event in events:
        home_team_id = await find_team_id(prefix, event.get("home_team", ""))
        away_team_id = await find_team_id(prefix, event.get("away_team", ""))

        for market in event.get("markets", []):
            stat_field = stat_fields.get(market["key"])
            if not stat_field:
                continue

            for outcome in market.get("outcomes", []):
                player_name = outcome.get("player")
                point = outcome.get("point")
                if not player_name or point is None:
                    continue

                try:
                    player = await find_player_id(prefix, player_name, home_team_id) or await find_player_id(
                        prefix, player_name, away_team_id
                    )
                    if not player or not player.get("id"):
                        continue

                    opponent_id = away_team_id if player.get("team_id") == home_team_id else home_team_id
                    logs = await get_player_recent_stats(prefix, player["id"], seasons)
                    over = outcome.get("name") == "Over"
                    insights = build_player_insights(
                        logs, stat_field, point, over, opponent_id, INSIGHTS_LAST_N_GAMES
                    )
                    if insights:
                        outcome["insights"] = insights
                except Exception:
                    # Best-effort: si balldontlie falla para este jugador puntual,
                    # seguimos con el resto sin tumbar toda la respuesta.
                    continue


@app.get("/api/odds")
async def get_odds(
    sport: str = Query(..., description="futbol | tenis | beisbol | basquetbol"),
    min_odds: float = Query(..., gt=1.0, description="cuota minima, ej 1.5"),
    max_odds: float = Query(..., gt=1.0, description="cuota maxima, ej 1.8"),
    league: Optional[str] = Query(None, description="sport key especifico, ej soccer_epl"),
    event_id: Optional[str] = Query(None, description="id de un partido especifico"),
    markets: str = Query(DEFAULT_MARKETS, description="mercados separados por coma"),
    regions: Optional[str] = Query(None, description="regiones de bookmakers separadas por coma; si se omite, se usa la default segun el deporte"),
):
    """
    Endpoint principal: trae las cuotas para el deporte/liga/evento elegido
    y devuelve solo los mercados cuya cuota cae dentro de [min_odds, max_odds].
    """
    if min_odds > max_odds:
        raise HTTPException(status_code=400, detail="min_odds no puede ser mayor que max_odds")

    sport_key = sport.lower()
    group = SPORT_GROUPS.get(sport_key)
    if not group:
        raise HTTPException(status_code=400, detail=f"Deporte invalido: {sport}")

    requested_markets = [m.strip() for m in markets.split(",") if m.strip()]
    has_player_or_additional_markets = any(m not in FEATURED_MARKETS for m in requested_markets)

    if has_player_or_additional_markets and not event_id:
        raise HTTPException(
            status_code=400,
            detail="Los mercados de jugador (o adicionales) solo se pueden pedir eligiendo un evento especifico.",
        )

    # Si el usuario no manda regions explicitamente, usamos la mejor por defecto
    # para ese deporte (evita el caso MLB/NBA con regiones europeas sin cobertura).
    # Los mercados de jugador casi solo tienen cobertura de casas americanas.
    if regions:
        effective_regions = regions
    elif has_player_or_additional_markets:
        effective_regions = PLAYER_PROPS_REGIONS
    else:
        effective_regions = REGIONS_BY_SPORT.get(sport_key, DEFAULT_REGIONS)

    leagues_to_query = [league] if league else [l["key"] for l in await get_leagues(sport)]

    results = []
    quota_info = {}
    errors = []
    for league_key in leagues_to_query:
        cache_key = make_key("odds", league_key, event_id, markets, effective_regions)
        if cache_key in odds_cache:
            raw = odds_cache[cache_key]
        else:
            path = f"/sports/{league_key}/events/{event_id}/odds" if event_id else f"/sports/{league_key}/odds"
            params = {"markets": markets, "regions": effective_regions, "oddsFormat": "decimal"}
            try:
                raw, quota_info = await odds_api_get(path, params)
            except HTTPException as e:
                # Ya no lo escondemos: lo guardamos para poder diagnosticar
                # por que una liga puntual no trajo nada (ej. mercado no soportado).
                errors.append({"league": league_key, "status": e.status_code, "detail": e.detail})
                continue
            # el endpoint de un solo evento devuelve un dict, no una lista
            raw = [raw] if isinstance(raw, dict) else raw
            odds_cache[cache_key] = raw

        results.extend(_aggregate_and_filter_outcomes(raw, min_odds, max_odds))

    # Insights de % de acierto historico (best-effort, solo si hay
    # balldontlie configurado y es un deporte soportado por ahora).
    if event_id and sport_key in BDL_SPORT_PREFIX:
        try:
            await _enrich_events_with_player_insights(sport_key, results)
        except Exception:
            pass

    return {
        "filters": {
            "sport": sport,
            "league": league,
            "event_id": event_id,
            "min_odds": min_odds,
            "max_odds": max_odds,
            "markets": markets,
            "regions": effective_regions,
        },
        "quota": quota_info,
        "count": len(results),
        "events": results,
        "errors": errors,
        "insights_enabled": bool(BALLDONTLIE_API_KEY),
    }
