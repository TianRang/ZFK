from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.models import Product, User
from app.templating import templates

router = APIRouter(prefix="/products")


@router.get("", response_class=HTMLResponse)
async def list_products(
    request: Request, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Product).order_by(Product.id.desc()))
    products = result.scalars().all()
    return templates.TemplateResponse("admin/products.html", {
        "request": request, "user": user.username, "products": products,
    })


@router.get("/add", response_class=HTMLResponse)
async def add_form(request: Request, user: User = Depends(get_current_user)):
    return templates.TemplateResponse("admin/product_form.html", {
        "request": request, "user": user.username, "editing": False,
    })


@router.post("/add")
async def add_submit(
    request: Request,
    user: User = Depends(get_current_user),
    name: str = Form(...),
    stock: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    name = name.strip()
    if not name:
        return templates.TemplateResponse("admin/product_form.html", {
            "request": request, "user": user.username, "editing": False,
            "error": request.state.t("err.product_form.empty_name"),
        })

    existing = await db.execute(select(Product).where(Product.name == name))
    if existing.scalar_one_or_none():
        return templates.TemplateResponse("admin/product_form.html", {
            "request": request, "user": user.username, "editing": False,
            "error": request.state.t("err.product_form.duplicate"), "name": name, "stock": stock,
        })

    lines = [l for l in stock.split("\n") if l.strip()]
    content = "\n".join(l.strip() for l in lines)
    total = len(lines)

    db.add(Product(name=name, stock=content, total_stock=total, used_stock=0))
    await db.commit()
    return RedirectResponse(f"{settings.admin_prefix}/products", status_code=302)


@router.get("/{product_id}/edit", response_class=HTMLResponse)
async def edit_form(
    product_id: int, request: Request,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        return RedirectResponse(f"{settings.admin_prefix}/products", status_code=302)
    return templates.TemplateResponse("admin/product_form.html", {
        "request": request, "user": user.username, "editing": True,
        "product": product, "name": product.name, "stock": product.stock,
    })


@router.post("/{product_id}/edit")
async def edit_submit(
    product_id: int, request: Request,
    user: User = Depends(get_current_user),
    name: str = Form(...),
    stock: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        return RedirectResponse(f"{settings.admin_prefix}/products", status_code=302)

    name = name.strip()
    if not name:
        return templates.TemplateResponse("admin/product_form.html", {
            "request": request, "user": user.username, "editing": True,
            "product": product, "error": request.state.t("err.product_form.empty_name"), "name": name, "stock": stock,
        })

    if name != product.name:
        dup = await db.execute(select(Product).where(Product.name == name))
        if dup.scalar_one_or_none():
            return templates.TemplateResponse("admin/product_form.html", {
                "request": request, "user": user.username, "editing": True,
                "product": product, "error": request.state.t("err.product_form.duplicate"), "name": name, "stock": stock,
            })

    lines = [l for l in stock.split("\n") if l.strip()]
    new_content = "\n".join(l.strip() for l in lines)
    new_total = len(lines) + product.used_stock

    product.name = name
    product.stock = new_content
    product.total_stock = new_total
    await db.commit()
    return RedirectResponse(f"{settings.admin_prefix}/products", status_code=302)


@router.post("/{product_id}/delete")
async def delete(
    product_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if product:
        await db.delete(product)
        await db.commit()
    return RedirectResponse(f"{settings.admin_prefix}/products", status_code=302)
