import os
from dotenv import load_dotenv

load_dotenv()

ODDS_API_KEY = os.getenv("ODDS_API_KEY", "")
ODDS_API_BASE = "https://api.the-odds-api.com/v4"

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
