import re
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api_auth import generate_api_key
from app.auth import hash_password, verify_password
from app.config import settings as app_settings
from app.database import get_db
from app.deps import get_current_user
from app.models import ApiKey, User
from app.site_settings import get_settings, save_setting
from app.templating import templates


def _runtime_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


router = APIRouter(prefix="/settings")


async def _list_api_keys(db: AsyncSession):
    rows = (await db.execute(select(ApiKey).order_by(ApiKey.id.desc()))).scalars().all()
    return rows


async def _build_ctx(request: Request, user: User, db: AsyncSession, **extra):
    site = await get_settings(db)
    api_keys = await _list_api_keys(db)
    ctx = {
        "request": request, "user": user.username, "site": site,
        "current_user": user, "current_prefix": app_settings.admin_prefix,
        "api_keys": api_keys,
    }
    ctx.update(extra)
    return ctx


@router.get("", response_class=HTMLResponse)
async def settings_page(request: Request, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    ctx = await _build_ctx(request, user, db)
    return templates.TemplateResponse("admin/settings.html", ctx)


@router.post("/site")
async def update_site(
    request: Request,
    site_name: str = Form(...),
    site_subtitle: str = Form(""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await save_setting(db, "site_name", site_name.strip())
    await save_setting(db, "site_subtitle", site_subtitle.strip())
    site = await get_settings(db)
    request.state.site = site
    ctx = await _build_ctx(request, user, db, site_success=True)
    return templates.TemplateResponse("admin/settings.html", ctx)


ALLOWED_TEMPLATES = {"default", "cartoon", "mario"}


@router.post("/template")
async def update_template(
    request: Request,
    front_template: str = Form(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    chosen = front_template if front_template in ALLOWED_TEMPLATES else "default"
    await save_setting(db, "front_template", chosen)
    site = await get_settings(db)
    request.state.site = site
    ctx = await _build_ctx(request, user, db, tpl_success=True)
    return templates.TemplateResponse("admin/settings.html", ctx)


@router.post("/prefix")
async def update_prefix(
    request: Request,
    admin_prefix: str = Form(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    prefix = admin_prefix.strip()
    if not prefix.startswith("/"):
        prefix = "/" + prefix
    prefix = re.sub(r"[^a-zA-Z0-9/_-]", "", prefix)
    if not prefix or prefix == "/":
        prefix = "/admin"

    env_path = _runtime_root() / ".env"
    try:
        if env_path.exists():
            content = env_path.read_text(encoding="utf-8")
            if "ADMIN_PREFIX=" in content:
                content = re.sub(r"ADMIN_PREFIX=.*", f"ADMIN_PREFIX={prefix}", content)
            else:
                content = content.rstrip() + f"\nADMIN_PREFIX={prefix}\n"
        else:
            content = f"ADMIN_PREFIX={prefix}\n"
        env_path.write_text(content, encoding="utf-8")
    except OSError as exc:
        ctx = await _build_ctx(
            request, user, db,
            current_prefix=prefix,
            prefix_error=f"无法写入 .env：{exc}",
        )
        return templates.TemplateResponse("admin/settings.html", ctx)

    ctx = await _build_ctx(request, user, db, current_prefix=prefix, prefix_success=True)
    return templates.TemplateResponse("admin/settings.html", ctx)


@router.post("/password")
async def update_password(
    request: Request,
    old_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(old_password, user.password_hash):
        ctx = await _build_ctx(request, user, db, pwd_error="原密码错误")
        return templates.TemplateResponse("admin/settings.html", ctx)

    if new_password != confirm_password:
        ctx = await _build_ctx(request, user, db, pwd_error="两次密码不一致")
        return templates.TemplateResponse("admin/settings.html", ctx)

    if len(new_password) < 6:
        ctx = await _build_ctx(request, user, db, pwd_error="密码至少6位")
        return templates.TemplateResponse("admin/settings.html", ctx)

    user.password_hash = hash_password(new_password)
    await db.commit()
    return RedirectResponse(f"{app_settings.admin_prefix}/settings#password", status_code=302)


@router.post("/api-keys/create")
async def create_api_key(
    request: Request,
    name: str = Form(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    name = name.strip() or "未命名"
    plaintext, prefix, digest = generate_api_key()
    db.add(ApiKey(name=name, key_prefix=prefix, key_hash=digest, is_active=True))
    await db.commit()
    ctx = await _build_ctx(request, user, db, api_new_key=plaintext, api_new_name=name)
    return templates.TemplateResponse("admin/settings.html", ctx)


@router.post("/api-keys/{key_id}/toggle")
async def toggle_api_key(
    key_id: int, request: Request,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(select(ApiKey).where(ApiKey.id == key_id))).scalar_one_or_none()
    if row:
        row.is_active = not row.is_active
        await db.commit()
    return RedirectResponse(f"{app_settings.admin_prefix}/settings#api", status_code=302)


@router.post("/api-keys/{key_id}/delete")
async def delete_api_key(
    key_id: int, request: Request,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(select(ApiKey).where(ApiKey.id == key_id))).scalar_one_or_none()
    if row:
        await db.delete(row)
        await db.commit()
    return RedirectResponse(f"{app_settings.admin_prefix}/settings#api", status_code=302)

