# 自助发卡系统

轻量级自助发卡网站，基于 Python + FastAPI 构建，支持多种卡密类型和自定义配色。

## 功能特性

- **多种卡密类型**
  - 通用类型：输入卡密直接显示内容
  - 点数类型：卡密自带库存，按需提取指定数量
  - 共享库存类型：多张卡密共享商品库存池，适合账号类商品
- **商品管理**：统一管理库存池，支持追加库存
- **卡密描述**：可为卡密添加使用说明或教程链接，提取时展示给用户
- **对外 API**：在「系统设置 → API 接口」创建 API Key，通过 `X-API-Key` 调用 `/api/v1/*` 完成卡密增删查、商品库存追加、统计查询等操作；API 文档页 `/admin/api-docs` 仅登录态可访问
- **验证码保护**：前台提取和后台登录均有验证码防护，验证码自带 10 分钟 TTL 与上限保护
- **前台多模板**：内置 `default` / `cartoon` / `mario` 三套前台风格，后台一键切换
- **自定义后台路径**：在系统设置中修改 `ADMIN_PREFIX` 并自动写回 `.env`，重启后生效
- **响应式设计**：适配桌面、平板、手机
- **SQLite 数据库**：零配置，开箱即用，也支持 MySQL / PostgreSQL
- **安全默认值**：JWT 密钥占位符会在首次启动时自动生成强随机串并写回 `.env`；Cookie 默认带 `HttpOnly` + `SameSite=lax`；前台提取在并发场景下用 per-card / per-product 锁 + 抢占式 UPDATE 防止额度透支

## 技术栈

- Python 3.10+
- FastAPI + Uvicorn
- SQLAlchemy (async) + aiosqlite
- Jinja2 模板引擎
- 纯 CSS（无框架依赖）

## 快速开始

### 环境要求

- Python 3.10 或更高版本
- pip

### 安装

```bash
# 克隆项目
git clone https://github.com/TianRang/ZFK.git
cd ZFK

# 创建虚拟环境（推荐）
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/macOS
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 配置

复制环境变量示例文件并修改：

```bash
cp .env.example .env
```

编辑 `.env` 文件：

```env
DATABASE_URL=sqlite+aiosqlite:///./data.db
JWT_SECRET=
SERVER_HOST=0.0.0.0
SERVER_PORT=3000
ADMIN_PREFIX=/admin
```

> `JWT_SECRET` 留空或保留示例占位符时，应用首次启动会自动生成 64 字节强随机密钥并写回 `.env`。要使用自定义值，直接覆盖即可。

### 运行

```bash
python run.py
```

服务启动后：
- 前台页面：`http://localhost:3000/`
- 后台管理：`http://localhost:3000/admin/`（首次访问需注册管理员账号）
- API 文档：`http://localhost:3000/admin/api-docs`（需先登录）

### 生产部署

```bash
# 不使用 reload 模式
uvicorn app.main:app --host 0.0.0.0 --port 3000
```

建议配合 Nginx 反向代理和 systemd 管理进程。

> 多 worker 部署提示：当前验证码缓存与站点设置缓存为单进程内存，开多 worker（`--workers N`）会出现验证码偶发不通过、设置变更延迟可见的问题。如需多 worker，建议先把这两处缓存换成 Redis 或类似集中存储。

## 打包为 EXE

可以将项目打包为单个 exe 文件，直接放到服务器上运行，无需安装 Python 环境。

### 方式一：PyInstaller（推荐）

```bash
# 安装 PyInstaller
pip install pyinstaller

# 打包（单文件模式）
pyinstaller --onefile --name zfk --icon=static/icon.ico \
  --add-data "templates:templates" \
  --add-data "static:static" \
  --add-data ".env.example:.env.example" \
  --hidden-import aiosqlite \
  --hidden-import uvicorn.logging \
  --hidden-import uvicorn.loops.auto \
  --hidden-import uvicorn.protocols.http.auto \
  --hidden-import uvicorn.protocols.websockets.auto \
  --hidden-import uvicorn.lifespan.on \
  run.py
```

Windows 下 `--add-data` 用分号分隔：

```bash
pyinstaller --onefile --name zfk --icon=static/icon.ico ^
  --add-data "templates;templates" ^
  --add-data "static;static" ^
  --add-data ".env.example;." ^
  --hidden-import aiosqlite ^
  --hidden-import uvicorn.logging ^
  --hidden-import uvicorn.loops.auto ^
  --hidden-import uvicorn.protocols.http.auto ^
  --hidden-import uvicorn.protocols.websockets.auto ^
  --hidden-import uvicorn.lifespan.on ^
  run.py
```

打包完成后在 `dist/` 目录下生成 `zfk.exe`（或 `zfk`）。

### 方式二：Nuitka（性能更好）

```bash
# 安装 Nuitka
pip install nuitka

# 打包
nuitka --onefile --output-filename=zfk \
  --include-data-dir=templates=templates \
  --include-data-dir=static=static \
  run.py
```

### 使用打包后的程序

1. 将 `zfk.exe`（或 `zfk`）上传到服务器
2. 同目录下创建 `.env` 文件（参考 `.env.example`）
3. 直接运行即可：

```bash
# Windows
zfk.exe

# Linux
chmod +x zfk
./zfk
```

首次运行会自动创建 `data.db` 数据库文件。

> **注意**：PyInstaller 单文件模式会将资源解压到临时目录，需要修改 `run.py` 以正确定位资源路径。见下方说明。

### EXE 模式路径适配

打包为 exe 后，`templates` 和 `static` 目录的路径需要适配。将 `run.py` 替换为以下内容：

```python
import os
import sys

import uvicorn

def get_base_path():
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

if __name__ == "__main__":
    base = get_base_path()
    os.chdir(base)
    from app.config import settings
    uvicorn.run("app.main:app", host=settings.server_host, port=settings.server_port)
```

这样 exe 运行时能正确找到模板和静态文件。

## 项目结构

```
zfk/
├── app/
│   ├── main.py            # 应用入口，路由注册与中间件
│   ├── config.py          # 配置管理（含 JWT_SECRET 自动生成）
│   ├── database.py        # 数据库连接
│   ├── models/            # 数据模型（User / CardKey / Product / SiteSettings / ApiKey）
│   ├── routers/           # 路由模块
│   │   ├── front.py       # 前台提取页面（支持 default / cartoon / mario 模板切换）
│   │   ├── auth.py        # 登录注册
│   │   ├── dashboard.py   # 仪表盘
│   │   ├── cards.py       # 卡密管理
│   │   ├── products.py    # 商品管理
│   │   ├── settings.py    # 系统设置（站点、模板、后台路径、API Key、密码）
│   │   ├── api.py         # 对外 JSON API（/api/v1/*）
│   │   └── api_docs.py    # API 文档页（/admin/api-docs，需登录）
│   ├── auth.py            # JWT 认证
│   ├── api_auth.py        # API Key 生成与校验（SHA-256 摘要存库）
│   ├── captcha.py         # 验证码生成（带 TTL 与上限）
│   ├── deps.py            # 依赖注入
│   ├── site_settings.py   # 站点设置缓存
│   └── templating.py      # 模板配置
├── templates/
│   ├── front/             # 前台模板（index / cartoon / mario）
│   ├── admin/             # 后台模板（含 settings、api_docs 等）
│   └── auth/              # 认证页面模板
├── static/
│   ├── css/app.css        # 样式文件
│   └── js/                # 前端脚本（轮盘 shell、面板路由、波纹特效）
├── requirements.txt       # Python 依赖
├── run.py                 # 启动脚本
├── .env.example           # 环境变量示例
└── .gitignore
```

## 数据库支持

默认使用 SQLite，无需额外配置。也支持 MySQL 和 PostgreSQL，修改 `.env` 中的 `DATABASE_URL` 并安装对应驱动即可：

```bash
# MySQL
pip install aiomysql
# .env: DATABASE_URL=mysql+aiomysql://user:pass@localhost/dbname

# PostgreSQL
pip install asyncpg
# .env: DATABASE_URL=postgresql+asyncpg://user:pass@localhost/dbname
```

## 环境变量说明

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DATABASE_URL` | 数据库连接地址 | `sqlite+aiosqlite:///./data.db` |
| `JWT_SECRET` | JWT 签名密钥；留空或为占位符时启动时自动生成并写回 `.env` | 自动生成 |
| `JWT_EXPIRE_HOURS` | Token 过期时间（小时） | `24` |
| `SERVER_HOST` | 监听地址 | `0.0.0.0` |
| `SERVER_PORT` | 监听端口 | `3000` |
| `ADMIN_PREFIX` | 后台路径前缀 | `/admin` |

## 使用说明

### 卡密类型

**通用类型**：适合一次性内容（如兑换码、下载链接）。用户输入卡密后直接显示全部内容。

**点数类型**：适合多条内容按需提取（如账号池）。每行内容算 1 点额度，用户可选择提取数量。

**共享库存类型**：适合多张卡密共享同一批商品。先创建商品并录入库存，再创建卡密绑定商品并设置额度。多张卡密从同一库存池发货。

### 批量添加格式

```
卡密|内容                           # 通用类型
卡密|points|账号1;;账号2;;账号3      # 点数类型
卡密|shared_stock|商品名|额度        # 共享库存类型
```

### 对外 API

后台「系统设置 → API 接口」可以创建 API Key，用于对接外部系统：

- 鉴权：在请求头加 `X-API-Key: zfk_xxxxx`，或 `Authorization: Bearer zfk_xxxxx`
- Base URL：`http://your-domain` + `/api/v1`
- API Key 仅在创建时显示一次，数据库内只保留 SHA-256 摘要；停用或删除即时生效
- 详细接口文档与示例见登录后访问的 `/admin/api-docs`

常用接口：

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET`    | `/api/v1/ping` | 健康检查 / Key 校验 |
| `GET`    | `/api/v1/stats` | 卡密、商品总数 |
| `GET`    | `/api/v1/cards` | 分页查询卡密（支持 `key` 模糊与 `card_type` 过滤） |
| `GET`    | `/api/v1/cards/{id}` 或 `/cards/by-key/{key}` | 查询单条 |
| `POST`   | `/api/v1/cards` | 创建卡密（支持 `normal` / `points` / `shared_stock`） |
| `DELETE` | `/api/v1/cards/{id}` 或 `/cards/by-key/{key}` | 删除卡密 |
| `GET`    | `/api/v1/products` | 商品列表 |
| `GET`    | `/api/v1/products/{id}` | 单个商品 |
| `POST`   | `/api/v1/products/{id}/stock` | 追加库存（不会重置 used_stock） |

调用示例：

```bash
curl -H "X-API-Key: zfk_xxxxx" http://localhost:3000/api/v1/ping

curl -X POST http://localhost:3000/api/v1/cards \
  -H "X-API-Key: zfk_xxxxx" \
  -H "Content-Type: application/json" \
  -d '{"key":"ABC123","card_type":"normal","content":"卡密内容"}'
```

## License

MIT
