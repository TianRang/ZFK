from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api_auth import require_api_key
from app.database import get_db
from app.models import ApiKey, CardKey, Product

router = APIRouter(prefix="/api/v1", tags=["api"])


# ---------- Schemas ----------

class CardCreate(BaseModel):
    key: str = Field(..., min_length=1, max_length=200)
    card_type: str = Field("normal", description="normal | points | shared_stock")
    content: str = Field("", max_length=200000)
    description: str = Field("", max_length=2000)
    product_id: Optional[int] = None
    total_points: int = Field(0, ge=0, le=10_000_000)


class CardOut(BaseModel):
    id: int
    key: str
    card_type: str
    content: str
    description: str
    total_points: int
    used_points: int
    remaining: int
    product_id: Optional[int]
    created_at: Optional[str]


class StockAppend(BaseModel):
    stock: str = Field(..., min_length=1, max_length=500000, description="多行库存，每行一条")


class ProductOut(BaseModel):
    id: int
    name: str
    total_stock: int
    used_stock: int
    remaining: int


class OkResponse(BaseModel):
    ok: bool = True


# ---------- Helpers ----------

def _card_to_dict(card: CardKey) -> dict:
    remaining = (card.total_points - card.used_points) if card.card_type in ("points", "shared_stock") else 0
    return {
        "id": card.id,
        "key": card.key,
        "card_type": card.card_type,
        "content": card.content,
        "description": card.description,
        "total_points": card.total_points,
        "used_points": card.used_points,
        "remaining": remaining,
        "product_id": card.product_id,
        "created_at": card.created_at.isoformat() if card.created_at else None,
    }


def _product_to_dict(product: Product) -> dict:
    return {
        "id": product.id,
        "name": product.name,
        "total_stock": product.total_stock,
        "used_stock": product.used_stock,
        "remaining": max(0, product.total_stock - product.used_stock),
    }


# ---------- Auth probe ----------

@router.get("/ping")
async def ping(_: ApiKey = Depends(require_api_key)):
    return {"ok": True, "message": "pong"}


# ---------- Card keys ----------

@router.get("/cards")
async def list_cards(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    key: Optional[str] = None,
    card_type: Optional[str] = None,
    _: ApiKey = Depends(require_api_key),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(CardKey)
    count_stmt = select(func.count()).select_from(CardKey)
    if key:
        stmt = stmt.where(CardKey.key.like(f"%{key}%"))
        count_stmt = count_stmt.where(CardKey.key.like(f"%{key}%"))
    if card_type:
        stmt = stmt.where(CardKey.card_type == card_type)
        count_stmt = count_stmt.where(CardKey.card_type == card_type)

    total = (await db.execute(count_stmt)).scalar() or 0
    rows = (await db.execute(stmt.order_by(CardKey.id.desc()).offset((page - 1) * per_page).limit(per_page))).scalars().all()
    return {
        "ok": True,
        "page": page,
        "per_page": per_page,
        "total": total,
        "items": [_card_to_dict(c) for c in rows],
    }


@router.get("/cards/{card_id}")
async def get_card_by_id(card_id: int, _: ApiKey = Depends(require_api_key), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(CardKey).where(CardKey.id == card_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="卡密不存在")
    return {"ok": True, "card": _card_to_dict(row)}


@router.get("/cards/by-key/{key}")
async def get_card_by_key(key: str, _: ApiKey = Depends(require_api_key), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(CardKey).where(CardKey.key == key))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="卡密不存在")
    return {"ok": True, "card": _card_to_dict(row)}


@router.post("/cards", status_code=201)
async def create_card(
    payload: CardCreate,
    _: ApiKey = Depends(require_api_key),
    db: AsyncSession = Depends(get_db),
):
    key = payload.key.strip()
    card_type = payload.card_type if payload.card_type in ("normal", "points", "shared_stock") else "normal"
    content = payload.content.strip()
    description = payload.description.strip()

    if not key:
        raise HTTPException(status_code=400, detail="卡密不能为空")

    existing = (await db.execute(select(CardKey).where(CardKey.key == key))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="该卡密已存在")

    if card_type == "shared_stock":
        if not payload.product_id:
            raise HTTPException(status_code=400, detail="shared_stock 需要 product_id")
        if payload.total_points < 1:
            raise HTTPException(status_code=400, detail="shared_stock 需要 total_points >= 1")
        product = (await db.execute(select(Product).where(Product.id == payload.product_id))).scalar_one_or_none()
        if not product:
            raise HTTPException(status_code=404, detail="关联商品不存在")
        card = CardKey(
            key=key, content="", description=description, card_type="shared_stock",
            total_points=payload.total_points, used_points=0, product_id=payload.product_id,
        )
    elif card_type == "points":
        if not content:
            raise HTTPException(status_code=400, detail="points 需要 content")
        lines = [l for l in content.splitlines() if l.strip()]
        card = CardKey(
            key=key, content="\n".join(lines), description=description, card_type="points",
            total_points=len(lines), used_points=0,
        )
    else:
        if not content:
            raise HTTPException(status_code=400, detail="normal 需要 content")
        card = CardKey(
            key=key, content=content, description=description, card_type="normal",
            total_points=0, used_points=0,
        )

    db.add(card)
    await db.commit()
    await db.refresh(card)
    return {"ok": True, "card": _card_to_dict(card)}


@router.delete("/cards/{card_id}")
async def delete_card(card_id: int, _: ApiKey = Depends(require_api_key), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(CardKey).where(CardKey.id == card_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="卡密不存在")
    await db.delete(row)
    await db.commit()
    return {"ok": True}


@router.delete("/cards/by-key/{key}")
async def delete_card_by_key(key: str, _: ApiKey = Depends(require_api_key), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(CardKey).where(CardKey.key == key))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="卡密不存在")
    await db.delete(row)
    await db.commit()
    return {"ok": True}


# ---------- Products / stock ----------

@router.get("/products")
async def list_products(_: ApiKey = Depends(require_api_key), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Product).order_by(Product.id.desc()))).scalars().all()
    return {"ok": True, "items": [_product_to_dict(p) for p in rows]}


@router.get("/products/{product_id}")
async def get_product(product_id: int, _: ApiKey = Depends(require_api_key), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(Product).where(Product.id == product_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="商品不存在")
    return {"ok": True, "product": _product_to_dict(row)}


@router.post("/products/{product_id}/stock")
async def append_stock(
    product_id: int,
    payload: StockAppend,
    _: ApiKey = Depends(require_api_key),
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(select(Product).where(Product.id == product_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="商品不存在")
    new_lines = [l.strip() for l in payload.stock.splitlines() if l.strip()]
    if not new_lines:
        raise HTTPException(status_code=400, detail="stock 内容为空")

    existing = [l for l in row.stock.splitlines() if l.strip()] if row.stock else []
    merged = existing + new_lines
    row.stock = "\n".join(merged)
    row.total_stock = len(merged) + row.used_stock
    await db.commit()
    return {"ok": True, "added": len(new_lines), "product": _product_to_dict(row)}


# ---------- Stats ----------

@router.get("/stats")
async def stats(_: ApiKey = Depends(require_api_key), db: AsyncSession = Depends(get_db)):
    total_cards = (await db.execute(select(func.count()).select_from(CardKey))).scalar() or 0
    total_products = (await db.execute(select(func.count()).select_from(Product))).scalar() or 0
    return {"ok": True, "total_cards": total_cards, "total_products": total_products}
