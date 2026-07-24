from cachetools import TTLCache

# Tres caches separados porque cada tipo de dato tiene un ritmo de cambio distinto.
leagues_cache = TTLCache(maxsize=64, ttl=60 * 60)
events_cache = TTLCache(maxsize=256, ttl=60 * 5)
odds_cache = TTLCache(maxsize=512, ttl=60)


def make_key(*parts) -> str:
    return "|".join(str(p) for p in parts if p is not None)
