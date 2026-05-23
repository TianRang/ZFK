from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from app.i18n import COOKIE_MAX_AGE, COOKIE_NAME, SUPPORTED, _normalize

router = APIRouter()


@router.get("/lang/{code}")
async def switch_language(code: str, request: Request):
    norm = _normalize(code)
    target = request.headers.get("referer") or "/"
    if norm not in SUPPORTED:
        return RedirectResponse(target, status_code=302)

    response = RedirectResponse(target, status_code=302)
    response.set_cookie(
        COOKIE_NAME,
        norm,
        max_age=COOKIE_MAX_AGE,
        httponly=False,
        samesite="lax",
        path="/",
    )
    return response
