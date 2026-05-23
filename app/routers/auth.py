import uuid

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import create_token, hash_password, verify_password
from app.captcha import generate_captcha, verify_captcha
from app.config import settings
from app.database import get_db
from app.models import User
from app.templating import templates

router = APIRouter()


def _get_session_id(request: Request) -> str:
    sid = request.cookies.get("sid")
    if not sid:
        sid = uuid.uuid4().hex
    return sid


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    sid = _get_session_id(request)
    captcha_img = generate_captcha(sid)
    response = templates.TemplateResponse("auth/login.html", {
        "request": request, "captcha_img": captcha_img, "sid": sid,
    })
    response.set_cookie("sid", sid, httponly=True, samesite="lax", max_age=600)
    return response


@router.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    captcha: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    sid = _get_session_id(request)

    if not verify_captcha(sid, captcha):
        captcha_img = generate_captcha(sid)
        response = templates.TemplateResponse(
            "auth/login.html", {
                "request": request, "error": "验证码错误",
                "captcha_img": captcha_img, "sid": sid,
            }, status_code=400
        )
        response.set_cookie("sid", sid, httponly=True, samesite="lax", max_age=600)
        return response

    result = await db.execute(
        select(User).where(User.username == username, User.is_active == True)
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(password, user.password_hash):
        captcha_img = generate_captcha(sid)
        response = templates.TemplateResponse(
            "auth/login.html", {
                "request": request, "error": "用户名或密码错误",
                "captcha_img": captcha_img, "sid": sid,
            }, status_code=400
        )
        response.set_cookie("sid", sid, httponly=True, samesite="lax", max_age=600)
        return response

    token = create_token(user.id, user.username, user.role)
    response = RedirectResponse(settings.admin_prefix, status_code=302)
    response.set_cookie("token", token, httponly=True, samesite="lax", max_age=86400)
    return response


@router.post("/logout")
async def logout():
    response = RedirectResponse(f"{settings.admin_prefix}/login", status_code=302)
    response.delete_cookie("token")
    return response


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, db: AsyncSession = Depends(get_db)):
    user_count = await db.execute(select(func.count()).select_from(User))
    if user_count.scalar() > 0:
        return RedirectResponse(f"{settings.admin_prefix}/login", status_code=302)
    return templates.TemplateResponse("auth/register.html", {"request": request})


@router.post("/register")
async def register_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    user_count = await db.execute(select(func.count()).select_from(User))
    if user_count.scalar() > 0:
        return RedirectResponse(f"{settings.admin_prefix}/login", status_code=302)

    if password != password_confirm:
        return templates.TemplateResponse(
            "auth/register.html", {"request": request, "error": "两次密码输入不一致"}, status_code=400
        )
    if len(username) < 3 or len(password) < 6:
        return templates.TemplateResponse(
            "auth/register.html", {"request": request, "error": "用户名至少3位，密码至少6位"}, status_code=400
        )

    user = User(username=username, password_hash=hash_password(password), role="admin")
    db.add(user)
    await db.commit()

    return RedirectResponse(f"{settings.admin_prefix}/login", status_code=302)
