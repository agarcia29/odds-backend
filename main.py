from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from cache import events_cache, leagues_cache, make_key, odds_cache
from config import DEFAULT_MARKETS, DEFAULT_REGIONS, SPORT_GROUPS
from odds_client import odds_api_get

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


@app.get("/api/events")
async def get_events(
    sport: str = Query(..., description="futbol | tenis | beisbol | basquetbol"),
    league: Optional[str] = Query(None, description="sport key especifico, ej soccer_epl"),
):
    """
    Devuelve los eventos (partidos) disponibles. Si no se pasa 'league',
    junta los eventos de todas las ligas del deporte elegido.
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
    resultado por (mercado, nombre, punto), quedandose con la cuota MAS ALTA
    entre todas las casas que la ofrecen. No exponemos el nombre de la casa
    porque ninguna es colombiana; solo nos interesa el numero.

    Tambien calculamos el promedio de esa cuota entre casas, para poder
    marcar cuando la mejor cuota esta claramente por encima del promedio
    (senal de "valor").
    """
    filtered_events = []
    for event in odds_response:
        # market_key -> (name, point) -> lista de precios de todas las casas
        markets_acc: dict[str, dict[tuple, list]] = {}

        for bookmaker in event.get("bookmakers", []):
            for market in bookmaker.get("markets", []):
                market_key = market["key"]
                markets_acc.setdefault(market_key, {})
                for outcome in market.get("outcomes", []):
                    price = outcome.get("price")
                    if price is None:
                        continue
                    dedup_key = (outcome.get("name"), outcome.get("point"))
                    markets_acc[market_key].setdefault(dedup_key, []).append(price)

        result_markets = []
        for market_key, outcomes_dict in markets_acc.items():
            matching_outcomes = []
            for (name, point), prices in outcomes_dict.items():
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


@app.get("/api/odds")
async def get_odds(
    sport: str = Query(..., description="futbol | tenis | beisbol | basquetbol"),
    min_odds: float = Query(..., gt=1.0, description="cuota minima, ej 1.5"),
    max_odds: float = Query(..., gt=1.0, description="cuota maxima, ej 1.8"),
    league: Optional[str] = Query(None, description="sport key especifico, ej soccer_epl"),
    event_id: Optional[str] = Query(None, description="id de un partido especifico"),
    markets: str = Query(DEFAULT_MARKETS, description="mercados separados por coma"),
    regions: str = Query(DEFAULT_REGIONS, description="regiones de bookmakers separadas por coma"),
):
    """
    Endpoint principal: trae las cuotas para el deporte/liga/evento elegido
    y devuelve solo los mercados cuya cuota cae dentro de [min_odds, max_odds].
    """
    if min_odds > max_odds:
        raise HTTPException(status_code=400, detail="min_odds no puede ser mayor que max_odds")

    group = SPORT_GROUPS.get(sport.lower())
    if not group:
        raise HTTPException(status_code=400, detail=f"Deporte invalido: {sport}")

    leagues_to_query = [league] if league else [l["key"] for l in await get_leagues(sport)]

    results = []
    quota_info = {}
    for league_key in leagues_to_query:
        cache_key = make_key("odds", league_key, event_id, markets, regions)
        if cache_key in odds_cache:
            raw = odds_cache[cache_key]
        else:
            path = f"/sports/{league_key}/events/{event_id}/odds" if event_id else f"/sports/{league_key}/odds"
            params = {"markets": markets, "regions": regions, "oddsFormat": "decimal"}
            try:
                raw, quota_info = await odds_api_get(path, params)
            except HTTPException:
                continue
            # el endpoint de un solo evento devuelve un dict, no una lista
            raw = [raw] if isinstance(raw, dict) else raw
            odds_cache[cache_key] = raw

        results.extend(_aggregate_and_filter_outcomes(raw, min_odds, max_odds))

    return {
        "filters": {
            "sport": sport,
            "league": league,
            "event_id": event_id,
            "min_odds": min_odds,
            "max_odds": max_odds,
            "markets": markets,
            "regions": regions,
        },
        "quota": quota_info,
        "count": len(results),
        "events": results,
    }
