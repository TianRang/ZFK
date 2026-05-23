from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SiteSettings

DEFAULTS = {
    "site_name": "",
    "site_subtitle": "",
    "front_template": "default",
}

_cache: Optional[dict] = None


async def get_settings(db: AsyncSession) -> dict:
    global _cache
    if _cache is not None:
        return dict(_cache)
    result = await db.execute(select(SiteSettings))
    rows = result.scalars().all()
    settings = dict(DEFAULTS)
    for row in rows:
        settings[row.key] = row.value
    _cache = settings
    return dict(settings)


async def save_setting(db: AsyncSession, key: str, value: str):
    global _cache
    result = await db.execute(select(SiteSettings).where(SiteSettings.key == key))
    row = result.scalar_one_or_none()
    if row:
        row.value = value
    else:
        db.add(SiteSettings(key=key, value=value))
    await db.commit()
    _cache = None
