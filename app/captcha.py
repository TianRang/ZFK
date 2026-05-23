import base64
import random
import string
import time
from io import BytesIO

from captcha.image import ImageCaptcha

_image_captcha = ImageCaptcha(width=160, height=44)
_store: dict[str, tuple[str, float]] = {}
_warmed = False

CAPTCHA_TTL_SECONDS = 600          # 10 分钟内不验证就视作过期
CAPTCHA_STORE_MAX_ENTRIES = 5000   # 进程内最多保留多少条，超了按时间淘汰最旧的


def warmup() -> None:
    """预渲染一次，触发字体加载，避免首请求卡 30ms。"""
    global _warmed
    if _warmed:
        return
    buf = BytesIO()
    _image_captcha.write("0000", buf)
    _warmed = True


def _evict_expired(now: float) -> None:
    expired = [sid for sid, (_, exp) in _store.items() if exp <= now]
    for sid in expired:
        _store.pop(sid, None)


def _evict_overflow() -> None:
    if len(_store) <= CAPTCHA_STORE_MAX_ENTRIES:
        return
    # 按到期时间排序，剔除最早将过期的，留下最新的 N 条
    items = sorted(_store.items(), key=lambda kv: kv[1][1])
    overflow = len(_store) - CAPTCHA_STORE_MAX_ENTRIES
    for sid, _ in items[:overflow]:
        _store.pop(sid, None)


def generate_captcha(session_id: str) -> str:
    code = "".join(random.choices(string.digits, k=4))
    now = time.time()
    _evict_expired(now)
    _store[session_id] = (code, now + CAPTCHA_TTL_SECONDS)
    _evict_overflow()
    buf = BytesIO()
    _image_captcha.write(code, buf)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/png;base64,{b64}"


def verify_captcha(session_id: str, user_input: str) -> bool:
    entry = _store.pop(session_id, None)
    if not entry:
        return False
    code, expires_at = entry
    if expires_at <= time.time():
        return False
    return user_input.strip() == code
