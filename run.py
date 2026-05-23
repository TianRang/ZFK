import os
import sys

import uvicorn


def is_frozen():
    return getattr(sys, "frozen", False)


if __name__ == "__main__":
    if is_frozen():
        os.environ["_MEIPASS"] = sys._MEIPASS
        os.chdir(os.path.dirname(sys.executable))

    from app.config import settings

    if is_frozen():
        from app.main import app
        uvicorn.run(app, host=settings.server_host, port=settings.server_port)
    else:
        uvicorn.run("app.main:app", host=settings.server_host, port=settings.server_port, reload=True)
