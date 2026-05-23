import os
import secrets
import sys
from pathlib import Path

from pydantic_settings import BaseSettings

PLACEHOLDER_SECRET = "change-this-to-a-random-secret-key"


def _runtime_dir() -> Path:
    """PyInstaller frozen 模式下 .env 应该在可执行文件旁边，否则在项目根目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def _ensure_jwt_secret() -> None:
    """启动前检查 JWT_SECRET，占位符或缺失时生成一个并落到 .env。

    这样首次部署忘了改密钥时不会留下众所周知的默认值。后续运行会读到生成好的强密钥。
    """
    env_secret = os.environ.get("JWT_SECRET", "").strip()
    if env_secret and env_secret != PLACEHOLDER_SECRET:
        return

    env_path = _runtime_dir() / ".env"
    file_secret = ""
    lines: list[str] = []
    if env_path.exists():
        try:
            text = env_path.read_text(encoding="utf-8")
            lines = text.splitlines()
            for line in lines:
                if line.startswith("JWT_SECRET="):
                    file_secret = line.split("=", 1)[1].strip()
                    break
        except OSError:
            lines = []

    if file_secret and file_secret != PLACEHOLDER_SECRET:
        os.environ["JWT_SECRET"] = file_secret
        return

    new_secret = secrets.token_urlsafe(48)
    os.environ["JWT_SECRET"] = new_secret

    try:
        replaced = False
        for i, line in enumerate(lines):
            if line.startswith("JWT_SECRET="):
                lines[i] = f"JWT_SECRET={new_secret}"
                replaced = True
                break
        if not replaced:
            lines.append(f"JWT_SECRET={new_secret}")
        env_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    except OSError:
        pass


_ensure_jwt_secret()


class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./data.db"
    jwt_secret: str = PLACEHOLDER_SECRET
    jwt_expire_hours: int = 24
    server_host: str = "0.0.0.0"
    server_port: int = 3000
    upload_dir: str = "static/uploads"
    max_upload_size: int = 5242880
    admin_prefix: str = "/admin"

    class Config:
        env_file = ".env"


settings = Settings()

if settings.jwt_secret == PLACEHOLDER_SECRET:
    settings.jwt_secret = secrets.token_urlsafe(48)
