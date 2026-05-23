import asyncio
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.captcha import generate_captcha, verify_captcha
from app.database import get_db
from app.models import CardKey, Product
from app.templating import templates

router = APIRouter()

# 同进程内串行化「读 → 切片 → 写回」环节，分别按 card.id 与 product.id 加锁
_card_locks: dict[int, asyncio.Lock] = {}
_product_locks: dict[int, asyncio.Lock] = {}


def _card_lock(card_id: int) -> asyncio.Lock:
    lock = _card_locks.get(card_id)
    if lock is None:
        lock = asyncio.Lock()
        _card_locks[card_id] = lock
    return lock


def _product_lock(product_id: int) -> asyncio.Lock:
    lock = _product_locks.get(product_id)
    if lock is None:
        lock = asyncio.Lock()
        _product_locks[product_id] = lock
    return lock


def _get_session_id(request: Request) -> str:
    sid = request.cookies.get("sid")
    if not sid:
        sid = uuid.uuid4().hex
    return sid


_TEMPLATE_MAP = {
    "default": "front/index.html",
    "cartoon": "front/cartoon.html",
    "mario": "front/mario.html",
}


def _render(request, ctx, sid):
    site = ctx.get("front_template") or (request.state.site or {}).get("front_template") or "default"
    tpl_name = _TEMPLATE_MAP.get(site, _TEMPLATE_MAP["default"])
    response = templates.TemplateResponse(tpl_name, ctx)
    response.set_cookie("sid", sid, httponly=True, samesite="lax", max_age=600)
    return response


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    sid = _get_session_id(request)
    site = request.state.site or {}
    captcha_img = generate_captcha(sid)
    return _render(request, {
        "request": request, "captcha_img": captcha_img, "sid": sid, **site,
    }, sid)


@router.post("/", response_class=HTMLResponse)
async def retrieve(
    request: Request,
    key: str = Form(...),
    captcha: str = Form(""),
    amount: Optional[int] = Form(None),
    step: str = Form("1"),
    db: AsyncSession = Depends(get_db),
):
    site = request.state.site or {}
    sid = _get_session_id(request)

    def ctx_form(**kw):
        return {
            "request": request, "captcha_img": generate_captcha(sid),
            "sid": sid, **site, **kw,
        }

    def ctx_plain(**kw):
        return {"request": request, "sid": sid, **site, **kw}

    if step == "1":
        if not verify_captcha(sid, captcha):
            return _render(request, ctx_form(error="验证码错误", key=key), sid)

        key = key.strip()
        if not key:
            return _render(request, ctx_form(error="请输入卡密"), sid)

        result = await db.execute(select(CardKey).where(CardKey.key == key))
        card = result.scalar_one_or_none()

        if not card:
            return _render(request, ctx_form(error="卡密不存在，请检查输入", key=key), sid)

        if card.card_type in ("points", "shared_stock"):
            remaining = card.total_points - card.used_points
            if remaining <= 0:
                return _render(request, ctx_form(error="该卡密额度已用完", key=key), sid)
            return _render(request, ctx_plain(
                key=key, points_step=True, remaining=remaining,
                card_description=card.description,
            ), sid)
        else:
            return _render(request, ctx_plain(
                content=card.content, key=key, card_description=card.description,
            ), sid)

    elif step == "2":
        key = key.strip()
        if not key or amount is None or amount < 1:
            return _render(request, ctx_form(error="请输入有效的提取数量", key=key), sid)

        result = await db.execute(select(CardKey).where(CardKey.key == key))
        card = result.scalar_one_or_none()

        if not card or card.card_type not in ("points", "shared_stock"):
            return _render(request, ctx_form(error="卡密无效", key=key), sid)

        if card.card_type == "shared_stock":
            async with _card_lock(card.id), _product_lock(card.product_id or 0):
                # 在锁内重新加载 card / product，确保读到最新 used_points / stock
                card = (await db.execute(
                    select(CardKey).where(CardKey.id == card.id)
                )).scalar_one_or_none()
                if not card:
                    return _render(request, ctx_form(error="卡密无效", key=key), sid)

                remaining = card.total_points - card.used_points
                if remaining <= 0:
                    return _render(request, ctx_form(error="该卡密额度已用完", key=key), sid)
                if amount > remaining:
                    return _render(request, ctx_plain(
                        error=f"提取数量超出剩余额度（剩余 {remaining}）",
                        key=key, points_step=True, remaining=remaining,
                    ), sid)

                product = (await db.execute(
                    select(Product).where(Product.id == card.product_id)
                )).scalar_one_or_none()
                if not product:
                    return _render(request, ctx_form(error="关联商品不存在", key=key), sid)

                stock_lines = [l for l in product.stock.split("\n") if l.strip()]
                if len(stock_lines) < amount:
                    return _render(request, ctx_plain(
                        error=f"商品库存不足（当前库存 {len(stock_lines)}）",
                        key=key, points_step=True, remaining=remaining,
                    ), sid)

                # 抢占式更新 card.used_points：仅当未超额时成功
                claim = await db.execute(
                    update(CardKey)
                    .where(
                        CardKey.id == card.id,
                        CardKey.used_points + amount <= CardKey.total_points,
                    )
                    .values(used_points=CardKey.used_points + amount)
                )
                if claim.rowcount != 1:
                    await db.rollback()
                    return _render(request, ctx_form(error="额度不足，请刷新后重试", key=key), sid)

                extracted = stock_lines[:amount]
                product.stock = "\n".join(stock_lines[amount:])
                product.used_stock += amount
                await db.commit()

                return _render(request, ctx_plain(
                    content="\n".join(extracted), key=key,
                    extract_info=f"已提取 {amount} 条，剩余额度 {remaining - amount}",
                    card_description=card.description,
                ), sid)
        else:
            # points 类型：在 per-card 锁内做读-切片-写回，避免两个请求都抢到额度后切到同一份 content
            async with _card_lock(card.id):
                card = (await db.execute(
                    select(CardKey).where(CardKey.id == card.id)
                )).scalar_one_or_none()
                if not card:
                    return _render(request, ctx_form(error="卡密无效", key=key), sid)

                remaining = card.total_points - card.used_points
                if remaining <= 0:
                    return _render(request, ctx_form(error="该卡密额度已用完", key=key), sid)
                if amount > remaining:
                    return _render(request, ctx_plain(
                        error=f"提取数量超出剩余额度（剩余 {remaining}）",
                        key=key, points_step=True, remaining=remaining,
                    ), sid)

                claim = await db.execute(
                    update(CardKey)
                    .where(
                        CardKey.id == card.id,
                        CardKey.used_points + amount <= CardKey.total_points,
                    )
                    .values(used_points=CardKey.used_points + amount)
                )
                if claim.rowcount != 1:
                    await db.rollback()
                    return _render(request, ctx_form(error="额度不足，请刷新后重试", key=key), sid)

                lines = [l for l in (card.content or "").split("\n") if l.strip()]
                extracted = lines[:amount]
                new_content = "\n".join(lines[amount:])
                await db.execute(
                    update(CardKey).where(CardKey.id == card.id).values(content=new_content)
                )
                await db.commit()

                return _render(request, ctx_plain(
                    content="\n".join(extracted), key=key,
                    extract_info=f"已提取 {amount} 条，剩余 {remaining - amount} 条",
                    card_description=card.description,
                ), sid)

    return _render(request, ctx_form(error="无效请求"), sid)
