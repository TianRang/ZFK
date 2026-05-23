import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.database import engine, Base, async_session
from app.deps import RequiresLogin
from app.models import User, CardKey, Product, SiteSettings, ApiKey
from app.routers import auth, dashboard, cards, front, products, settings as settings_router, api as api_router, api_docs
from app.site_settings import get_settings
from app.captcha import warmup as captcha_warmup

_bundle_dir = os.environ.get("_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    captcha_warmup()
    yield
    await engine.dispose()


app = FastAPI(title="卡密发货系统", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


class SiteSettingsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith("/static"):
            try:
                async with async_session() as db:
                    request.state.site = await get_settings(db)
            except Exception:
                request.state.site = {}
        else:
            request.state.site = {}
        return await call_next(request)


app.add_middleware(SiteSettingsMiddleware)


@app.exception_handler(RequiresLogin)
async def requires_login_handler(request: Request, exc: RequiresLogin):
    return RedirectResponse(f"{settings.admin_prefix}/login")


app.mount("/static", StaticFiles(directory=os.path.join(_bundle_dir, "static")), name="static")

# 前端公开页面
app.include_router(front.router)

# 对外 API（通过 X-API-Key 校验）
app.include_router(api_router.router)

# 后台管理
app.include_router(auth.router, prefix=settings.admin_prefix)
app.include_router(dashboard.router, prefix=settings.admin_prefix)
app.include_router(cards.router, prefix=settings.admin_prefix)
app.include_router(products.router, prefix=settings.admin_prefix)
app.include_router(settings_router.router, prefix=settings.admin_prefix)
app.include_router(api_docs.router, prefix=settings.admin_prefix)
