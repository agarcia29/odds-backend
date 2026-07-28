import os
from dotenv import load_dotenv

load_dotenv()

ODDS_API_KEY = os.getenv("ODDS_API_KEY", "")
ODDS_API_BASE = "https://api.the-odds-api.com/v4"

# --- balldontlie (estadisticas historicas para calcular % de acierto) ---
BALLDONTLIE_API_KEY = os.getenv("BALLDONTLIE_API_KEY", "")
BALLDONTLIE_BASE = "https://api.balldontlie.io"

# Prefijo de URL de balldontlie por deporte. Empezamos solo con beisbol
# (coincide con el ejemplo que nos diste) y basquetbol; futbol/tenis se
# agregan despues siguiendo el mismo patron.
BDL_SPORT_PREFIX = {
    "beisbol": "mlb",
    "basquetbol": "nba",
}

# Cuantos partidos recientes mirar para calcular el % de acierto.
INSIGHTS_LAST_N_GAMES = 10

# OJO - PENDIENTE DE VERIFICAR CON DATOS REALES:
# Estos son los nombres de campo que balldontlie normalmente usa en su
# respuesta de estadisticas por partido, pero no se pudieron confirmar
# 100% sin hacer una llamada real con API key. En cuanto Andres tenga
# su key, hacemos una llamada de prueba y ajustamos esto si hace falta.
MARKET_STAT_FIELDS = {
    "beisbol": {
        "batter_hits": "hits",
        "batter_home_runs": "home_runs",
        "batter_rbis": "rbi",
        "pitcher_strikeouts": "strikeouts",
    },
    "basquetbol": {
        "player_points": "pts",
        "player_rebounds": "reb",
        "player_assists": "ast",
        "player_threes": "fg3m",
        "player_blocks": "blk",
        "player_steals": "stl",
    },
}


# Mapeo de "deporte" (como lo elige el usuario en la app) al campo "group"
# que devuelve The Odds API en GET /v4/sports. Esto permite mostrar 4
# botones simples (Futbol, Tenis, Beisbol, Basquetbol) y por debajo
# resolver todas las ligas (sport keys) que caen en ese grupo.
SPORT_GROUPS = {
    "futbol": "Soccer",
    "tenis": "Tennis",
    "beisbol": "Baseball",
    "basquetbol": "Basketball",
}

# Mercados soportados por defecto si el usuario no elige ninguno en particular.
DEFAULT_MARKETS = "h2h,spreads,totals"

# Regiones de bookmakers a consultar, AJUSTADAS POR DEPORTE. Las casas
# europeas (eu/uk) cubren muy bien futbol y tenis, pero casi no ofrecen
# MLB ni NBA (deportes 100% americanos) — ahi hay que pedir "us"/"us2".
# Si se pide "todas las ligas" de un deporte y se usa solo eu/uk para MLB,
# la mayoria de partidos vuelven sin ninguna cuota y parece que "no hay nada".
REGIONS_BY_SPORT = {
    "futbol": "eu,uk",
    "tenis": "eu,uk",
    "beisbol": "us,us2",
    "basquetbol": "us,us2,eu",
}
DEFAULT_REGIONS = "eu,uk"  # fallback si algun deporte no esta en el dict de arriba

# TTLs de cache (segundos) para no gastar cuota de la API en cada request.
LEAGUES_CACHE_TTL = 60 * 60       # 1 hora: la lista de ligas casi no cambia
EVENTS_CACHE_TTL = 60 * 5         # 5 minutos
ODDS_CACHE_TTL = 60               # 1 minuto: las cuotas cambian seguido

# Mercados de jugador ("player props"). Solo se pueden pedir por evento
# especifico (event_id obligatorio) y casi toda la cobertura es de casas
# americanas, por eso siempre se piden con regions=us,us2 sin importar
# el deporte. Tenis no tiene mercados de jugador en The Odds API todavia.
PLAYER_MARKETS_BY_SPORT = {
    "futbol": [
        {"key": "player_shots_on_target", "label": "Tiros al arco"},
        {"key": "player_shots", "label": "Tiros totales"},
        {"key": "player_goal_scorer_anytime", "label": "Anota en cualquier momento"},
        {"key": "player_assists", "label": "Asistencias"},
        {"key": "player_to_receive_card", "label": "Recibe tarjeta"},
    ],
    "basquetbol": [
        {"key": "player_points", "label": "Puntos"},
        {"key": "player_rebounds", "label": "Rebotes"},
        {"key": "player_assists", "label": "Asistencias"},
        {"key": "player_threes", "label": "Triples"},
        {"key": "player_blocks", "label": "Bloqueos"},
        {"key": "player_steals", "label": "Robos"},
        {"key": "player_points_rebounds_assists", "label": "Puntos + Rebotes + Asistencias"},
    ],
    "beisbol": [
        {"key": "batter_hits", "label": "Hits del bateador"},
        {"key": "batter_home_runs", "label": "Home runs del bateador"},
        {"key": "batter_rbis", "label": "Carreras impulsadas (RBI)"},
        {"key": "batter_total_bases", "label": "Bases totales"},
        {"key": "pitcher_strikeouts", "label": "Ponches del pitcher"},
    ],
    "tenis": [],  # The Odds API todavia no cubre player props de tenis
}

# Mercados "base" (featured); cualquier otra market key se considera
# "adicional" (incluye player props) y solo funciona pidiendo un evento puntual.
FEATURED_MARKETS = {"h2h", "spreads", "totals"}

# Mercados adicionales A NIVEL DE PARTIDO (no de jugador puntual). Por ahora
# The Odds API solo los soporta bien para futbol. NOTA: corners (tiros de
# esquina) NO esta disponible en esta API todavia, solo en otras de la
# competencia — no se puede ofrecer aunque se pidio.
MATCH_MARKETS_BY_SPORT = {
    "futbol": [
        {"key": "btts", "label": "Ambos equipos anotan"},
        {"key": "double_chance", "label": "Doble oportunidad"},
        {"key": "draw_no_bet", "label": "Empate anula (Draw No Bet)"},
    ],
    "basquetbol": [],
    "beisbol": [],
    "tenis": [],
}

# Regiones a forzar cuando se piden mercados de jugador, porque casi no
# hay cobertura fuera de casas americanas.
PLAYER_PROPS_REGIONS = "us,us2"
