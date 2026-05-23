import os

from starlette.requests import Request
from starlette.templating import Jinja2Templates

from app.config import settings
from app.i18n import DEFAULT_LANG, build_t

_bundle_dir = os.environ.get("_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _i18n_context(request: Request) -> dict:
    t = getattr(request.state, "t", None)
    lang = getattr(request.state, "lang", DEFAULT_LANG)
    if t is None:
        t = build_t(DEFAULT_LANG)
    return {"t": t, "lang": lang}


templates = Jinja2Templates(
    directory=os.path.join(_bundle_dir, "templates"),
    context_processors=[_i18n_context],
)
templates.env.globals["admin_prefix"] = settings.admin_prefix


def is_partial(request: Request) -> bool:
    if request.headers.get("x-partial") == "1":
        return True
    if request.query_params.get("partial") == "1":
        return True
    return False


templates.env.globals["is_partial"] = is_partial
