import hashlib
import secrets
from datetime import datetime, timezone

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import ApiKey

KEY_PLAINTEXT_PREFIX = "zfk_"


def generate_api_key() -> tuple[str, str, str]:
    """Returns (plaintext, prefix, sha256_hash). Plaintext is shown to user once."""
    raw = secrets.token_urlsafe(32)
    plaintext = f"{KEY_PLAINTEXT_PREFIX}{raw}"
    prefix = plaintext[:12]
    digest = hashlib.sha256(plaintext.encode()).hexdigest()
    return plaintext, prefix, digest


def hash_api_key(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode()).hexdigest()


async def require_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> ApiKey:
    token = x_api_key
    if not token and authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="缺少 API Key")

    digest = hash_api_key(token)
    result = await db.execute(select(ApiKey).where(ApiKey.key_hash == digest))
    record = result.scalar_one_or_none()
    if not record or not record.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API Key 无效或已禁用")

    await db.execute(
        update(ApiKey)
        .where(ApiKey.id == record.id)
        .values(total_calls=ApiKey.total_calls + 1, last_used_at=datetime.now(timezone.utc))
    )
    await db.commit()
    return record
