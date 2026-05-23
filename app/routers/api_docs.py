from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.config import settings as app_settings
from app.deps import get_current_user
from app.models import User
from app.templating import templates

router = APIRouter()


@router.get("/api-docs", response_class=HTMLResponse)
async def api_docs(request: Request, user: User = Depends(get_current_user)):
    base_url = str(request.base_url).rstrip("/")
    return templates.TemplateResponse("admin/api_docs.html", {
        "request": request,
        "user": user.username,
        "current_user": user,
        "base_url": base_url,
        "admin_prefix": app_settings.admin_prefix,
    })
