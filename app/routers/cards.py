from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.models import CardKey, Product, User
from app.templating import templates

router = APIRouter(prefix="/cards")


@router.get("", response_class=HTMLResponse)
async def list_cards(
    request: Request, page: int = 1, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    page = max(1, page)
    per_page = 50
    offset = (page - 1) * per_page

    result = await db.execute(select(CardKey).order_by(CardKey.id.desc()).offset(offset).limit(per_page))
    cards = result.scalars().all()

    product_ids = [c.product_id for c in cards if c.product_id]
    product_map = {}
    if product_ids:
        prod_result = await db.execute(select(Product).where(Product.id.in_(product_ids)))
        for p in prod_result.scalars().all():
            product_map[p.id] = p.name

    total_result = await db.execute(select(func.count()).select_from(CardKey))
    total = total_result.scalar()
    total_pages = max(1, -(-total // per_page))

    return templates.TemplateResponse("admin/cards.html", {
        "request": request, "user": user.username, "cards": cards,
        "page": page, "total_pages": total_pages, "total": total,
        "product_map": product_map,
    })


@router.get("/add", response_class=HTMLResponse)
async def add_form(request: Request, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    products = (await db.execute(select(Product).order_by(Product.name))).scalars().all()
    return templates.TemplateResponse("admin/card_form.html", {
        "request": request, "user": user.username, "products": products,
    })


@router.post("/add")
async def add_submit(
    request: Request,
    user: User = Depends(get_current_user),
    key: str = Form(...),
    content: str = Form(""),
    description: str = Form(""),
    card_type: str = Form("normal"),
    product_id: int = Form(0),
    total_points: int = Form(0),
    db: AsyncSession = Depends(get_db),
):
    key = key.strip()
    content = content.strip()
    description = description.strip()
    card_type = card_type if card_type in ("normal", "points", "shared_stock") else "normal"
    products = (await db.execute(select(Product).order_by(Product.name))).scalars().all()

    def form_ctx(**kw):
        return {
            "request": request, "user": user.username, "products": products,
            "key": key, "content": content, "card_type": card_type,
            "product_id": product_id, "total_points": total_points,
            "description": description, **kw,
        }

    if not key:
        return templates.TemplateResponse("admin/card_form.html", form_ctx(error="卡密不能为空"))

    if card_type == "shared_stock":
        if not product_id:
            return templates.TemplateResponse("admin/card_form.html", form_ctx(error="请选择关联商品"))
        if total_points < 1:
            return templates.TemplateResponse("admin/card_form.html", form_ctx(error="额度必须大于0"))
    elif card_type == "normal" and not content:
        return templates.TemplateResponse("admin/card_form.html", form_ctx(error="内容不能为空"))
    elif card_type == "points" and not content:
        return templates.TemplateResponse("admin/card_form.html", form_ctx(error="内容不能为空"))

    existing = await db.execute(select(CardKey).where(CardKey.key == key))
    if existing.scalar_one_or_none():
        return templates.TemplateResponse("admin/card_form.html", form_ctx(error="该卡密已存在"))

    if card_type == "points":
        lines = [l for l in content.split("\n") if l.strip()]
        tp = len(lines)
        content = "\n".join(lines)
        db.add(CardKey(key=key, content=content, description=description, card_type="points", total_points=tp, used_points=0))
    elif card_type == "shared_stock":
        db.add(CardKey(key=key, content="", description=description, card_type="shared_stock",
                       total_points=total_points, used_points=0, product_id=product_id))
    else:
        db.add(CardKey(key=key, content=content, description=description, card_type="normal", total_points=0, used_points=0))

    await db.commit()
    return RedirectResponse(f"{settings.admin_prefix}/cards", status_code=302)


@router.get("/batch", response_class=HTMLResponse)
async def batch_form(request: Request, user: User = Depends(get_current_user)):
    return templates.TemplateResponse("admin/card_batch.html", {"request": request, "user": user.username})


@router.post("/batch")
async def batch_submit(
    request: Request,
    user: User = Depends(get_current_user),
    data: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    lines = [l.strip() for l in data.strip().splitlines() if l.strip()]
    if not lines:
        return templates.TemplateResponse("admin/card_batch.html", {
            "request": request, "user": user.username, "error": "内容为空",
        })

    added = 0
    skipped = 0
    seen: set[str] = set()
    for line in lines:
        parts = line.split("|")
        if len(parts) < 2:
            skipped += 1
            continue

        type_hint = parts[1].strip().lower() if len(parts) >= 3 else ""

        if type_hint == "shared_stock" and len(parts) >= 4:
            k = parts[0].strip()
            product_name = parts[2].strip()
            try:
                quota = int(parts[3].strip())
            except ValueError:
                skipped += 1
                continue
            if not k or not product_name or quota < 1:
                skipped += 1
                continue
            if k in seen:
                skipped += 1
                continue
            existing = await db.execute(select(CardKey).where(CardKey.key == k))
            if existing.scalar_one_or_none():
                skipped += 1
                continue
            prod_result = await db.execute(select(Product).where(Product.name == product_name))
            product = prod_result.scalar_one_or_none()
            if not product:
                skipped += 1
                continue
            db.add(CardKey(key=k, content="", card_type="shared_stock",
                           total_points=quota, used_points=0, product_id=product.id))
            seen.add(k)
        elif type_hint == "points" and len(parts) >= 3:
            k = parts[0].strip()
            content_raw = "|".join(parts[2:]).strip()
            content_lines = [x.strip() for x in content_raw.split(";;") if x.strip()]
            if not k or not content_lines:
                skipped += 1
                continue
            if k in seen:
                skipped += 1
                continue
            existing = await db.execute(select(CardKey).where(CardKey.key == k))
            if existing.scalar_one_or_none():
                skipped += 1
                continue
            content = "\n".join(content_lines)
            db.add(CardKey(key=k, content=content, card_type="points",
                           total_points=len(content_lines), used_points=0))
            seen.add(k)
        else:
            k = parts[0].strip()
            c = "|".join(parts[1:]).strip()
            if not k or not c:
                skipped += 1
                continue
            if k in seen:
                skipped += 1
                continue
            existing = await db.execute(select(CardKey).where(CardKey.key == k))
            if existing.scalar_one_or_none():
                skipped += 1
                continue
            db.add(CardKey(key=k, content=c, card_type="normal", total_points=0, used_points=0))
            seen.add(k)

        added += 1

    await db.commit()
    return templates.TemplateResponse("admin/card_batch.html", {
        "request": request, "user": user.username,
        "success": f"成功添加 {added} 条，跳过 {skipped} 条",
    })


@router.post("/{card_id}/delete")
async def delete(card_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(CardKey).where(CardKey.id == card_id))
    card = result.scalar_one_or_none()
    if card:
        await db.delete(card)
        await db.commit()
    return RedirectResponse(f"{settings.admin_prefix}/cards", status_code=302)
