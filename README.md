# Odds Filter API

Backend en FastAPI que consulta The Odds API, cachea resultados y filtra
mercados por rango de cuota decimal (formato colombiano: 1.5, 1.8, etc).

## Correr localmente

```bash
cp .env.example .env
# edita .env y pon tu ODDS_API_KEY real
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Docs interactivas: http://localhost:8000/docs

## Endpoints

- `GET /api/sports` -> lista fija: futbol, tenis, beisbol, basquetbol
- `GET /api/leagues?sport=futbol` -> ligas disponibles para ese deporte
- `GET /api/events?sport=futbol&league=soccer_epl` -> partidos (league opcional)
- `GET /api/odds?sport=futbol&min_odds=1.5&max_odds=1.8&league=...&event_id=...`
  -> mercados filtrados por rango de cuota. `league` y `event_id` son opcionales.

## Desplegar en Render

1. Sube esta carpeta a un repo de GitHub.
2. En Render: New -> Web Service -> conecta el repo.
3. Render detecta `render.yaml` automaticamente (Blueprint), o configura a mano:
   - Build command: `pip install -r requirements.txt`
   - Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. En Environment, agrega la variable `ODDS_API_KEY` con tu key real.
5. Deploy. Tu URL quedara algo como `https://odds-filter-api.onrender.com`.

Esa URL es la que la app React Native va a usar como `API_BASE_URL`.

## Notas sobre cuota de The Odds API

- `/api/sports` y `/api/events` no consumen cuota.
- `/api/leagues` internamente llama a `/sports` (no consume cuota) y se cachea 1 hora.
- `/api/odds` SI consume cuota (1 credito por region x mercado solicitado, por liga).
  Se cachea 60 segundos por combinacion de liga+mercados+regiones para evitar
  gastar cuota si varios usuarios piden lo mismo casi al mismo tiempo, o si el
  mismo usuario mueve el slider de cuota rapido (el filtro se re-aplica sobre
  el cache, no dispara una llamada nueva).
