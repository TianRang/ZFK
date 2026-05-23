import os

from starlette.requests import Request
from starlette.templating import Jinja2Templates

from app.config import settings

_bundle_dir = os.environ.get("_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

templates = Jinja2Templates(directory=os.path.join(_bundle_dir, "templates"))
templates.env.globals["admin_prefix"] = settings.admin_prefix


def is_partial(request: Request) -> bool:
    if request.headers.get("x-partial") == "1":
        return True
    if request.query_params.get("partial") == "1":
        return True
    return False


templates.env.globals["is_partial"] = is_partial
