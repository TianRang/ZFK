from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user
from app.models import CardKey, Product, User
from app.templating import templates

router = APIRouter()


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def index(request: Request, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    total_cards = (await db.execute(select(func.count()).select_from(CardKey))).scalar()
    used_cards = (await db.execute(
        select(func.count()).select_from(CardKey).where(CardKey.used_points > 0)
    )).scalar()
    total_products = (await db.execute(select(func.count()).select_from(Product))).scalar()

    return templates.TemplateResponse("admin/dashboard.html", {
        "request": request,
        "user": user.username,
        "total_cards": total_cards,
        "used_cards": used_cards,
        "avail_cards": total_cards - used_cards,
        "total_products": total_products,
    })
