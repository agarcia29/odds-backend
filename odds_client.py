import httpx
from fastapi import HTTPException

from config import ODDS_API_BASE, ODDS_API_KEY


class OddsApiError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail


async def odds_api_get(path: str, params: dict) -> tuple[dict | list, dict]:
    """
    Hace GET contra The Odds API y devuelve (json, headers_utiles).
    headers_utiles incluye cuanta cuota queda (x-requests-remaining, etc.)
    para que el frontend pueda mostrar un aviso si se esta por acabar.
    """
    if not ODDS_API_KEY:
        raise HTTPException(status_code=500, detail="ODDS_API_KEY no configurada en el servidor")

    url = f"{ODDS_API_BASE}{path}"
    full_params = {"apiKey": ODDS_API_KEY, **params}

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, params=full_params)

    if resp.status_code != 200:
        # The Odds API devuelve el detalle del error en el body
        try:
            detail = resp.json().get("message", resp.text)
        except Exception:
            detail = resp.text
        raise HTTPException(status_code=resp.status_code, detail=detail)

    quota_info = {
        "requests_remaining": resp.headers.get("x-requests-remaining"),
        "requests_used": resp.headers.get("x-requests-used"),
    }
    return resp.json(), quota_info
