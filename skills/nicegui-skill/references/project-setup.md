# NiceGUI Project Setup & Scanning Reference

## Table of Contents
1. [Project Scanning Protocol](#1-project-scanning-protocol)
2. [Detecting Existing Patterns](#2-detecting-existing-patterns)
3. [Canonical Directory Structure](#3-canonical-directory-structure)
4. [Bootstrapping a New Project](#4-bootstrapping-a-new-project)
5. [Integrating Into an Existing Project](#5-integrating-into-an-existing-project)
6. [Environment & Config Files](#6-environment--config-files)
7. [requirements.txt Baseline](#7-requirementstxt-baseline)

---

## 1. Project Scanning Protocol

**Always run this scan before writing any code.** Use Glob and Read tools to map the project.

### Step 1: Root-level snapshot
```
Glob: **/* (maxdepth 2, skip node_modules/.venv/__pycache__)
```
Look for:
- `main.py` — entry point?
- `app.py` — existing Flask/FastAPI app?
- `requirements.txt` / `pyproject.toml` / `Pipfile` — dependencies
- `Dockerfile` / `docker-compose.yml` — deployment setup
- `.env` / `.env.example` — environment variables
- `README.md` — project description

### Step 2: Dependency check
Read `requirements.txt` or `pyproject.toml`. Identify:
- Is `nicegui` already a dependency?
- Is `fastapi` / `flask` / `django` present? (determines integration mode)
- Is there a DB library (`tortoise-orm`, `sqlalchemy`, `peewee`, `sqlite3`)?
- Are there any existing API clients (`httpx`, `aiohttp`, `requests`)?

### Step 3: Existing UI scan
If NiceGUI is already present:
```python
# Search for these patterns
grep: "ui.run", "@ui.page", "ui.colors", "from nicegui"
```
- Where is `ui.run()` called? That's `main.py`.
- Are there existing `@ui.page()` routes? List them.
- Is there an existing `ui.colors()` call? Read it — use those colors.
- Are there existing component files in `components/` or `pages/`?

### Step 4: API scan
```
grep: "@app.get", "@app.post", "@router", "APIRouter", "include_router"
```
- Is there a REST API already? List endpoints.
- Does it use FastAPI directly or a wrapper?
- What data models exist (`models.py`, `schemas.py`, Pydantic models)?

### Step 5: Styling scan
```
grep: "ui.colors", ".classes(", "add_css", "add_head_html"
```
- Extract the current color palette (primary, secondary, etc.)
- Note any custom CSS in `static/`

### Scan output format
After scanning, summarize:
```
Project: [name from README or dir name]
Type: [new NiceGUI project / existing NiceGUI / adding NiceGUI to FastAPI / etc.]
Entry point: [main.py or ...]
Existing pages: [list or "none"]
Existing API: [list key routes or "none"]
Colors: [primary/secondary or "not set yet"]
DB: [sqlite/postgres/none]
Docker: [yes/no]
Missing: [what needs to be created]
```

---

## 2. Detecting Existing Patterns

### Pattern: Pure NiceGUI project
```python
# Signs: ui.run() in main.py, no separate FastAPI app
ui.run(host='0.0.0.0', port=8080)
```
**Action:** Add pages/components alongside existing ones. Match nav and styling.

### Pattern: NiceGUI with FastAPI
```python
# Signs: separate FastAPI app + ui.run_with()
from fastapi import FastAPI
from nicegui import ui
fastapi_app = FastAPI()
ui.run_with(fastapi_app, mount_path='/ui')
```
**Action:** Add new UI routes via `APIRouter`. Add REST routes to `fastapi_app`. Don't create a second NiceGUI instance.

### Pattern: No NiceGUI yet (adding to existing project)
```python
# Signs: Flask/FastAPI app without nicegui import
from fastapi import FastAPI
app = FastAPI()
```
**Action:** Bootstrap NiceGUI alongside. Create `main.py` entry point, import existing app.

### Pattern: Fresh project (empty directory)
**Action:** Bootstrap full structure (see Section 4).

---

## 3. Canonical Directory Structure

This is the target structure for any non-trivial NiceGUI project:

```
project/
├── main.py                      # Entry point — ui.run() or ui.run_with()
├── config.py                    # Settings, constants, env vars
│
├── components/                  # Reusable UI building blocks
│   ├── __init__.py
│   ├── frame.py                 # app_frame() context manager (header/drawer/layout)
│   ├── cards.py                 # MetricCard, StatusCard, etc.
│   ├── tables.py                # DataTable wrapper, columns config
│   ├── forms.py                 # FormField, validated input groups
│   └── dialogs.py               # ConfirmDialog, EditDialog
│
├── pages/                       # Page content — one file per section
│   ├── __init__.py
│   ├── dashboard.py
│   ├── settings.py
│   └── *.py
│
├── routers/                     # APIRouter modules (REST + UI routes)
│   ├── __init__.py
│   ├── api.py                   # /api/* REST endpoints
│   └── auth.py                  # /login, /logout, /oauth
│
├── services/                    # Business logic, data access
│   ├── __init__.py
│   └── *.py
│
├── models/                      # DB models or Pydantic schemas
│   └── *.py
│
├── static/                      # Served at /static/*
│   ├── custom.css
│   └── *.{png,svg,ico}
│
├── .env                         # Secrets (never commit)
├── .env.example                 # Template (commit this)
├── requirements.txt
├── Dockerfile                   # Optional
└── docker-compose.yml           # Optional
```

**Minimal project** (single-purpose app):
```
project/
├── main.py
├── components/frame.py
├── static/
├── .env
└── requirements.txt
```

**Scale up** by adding directories only as needed. Don't create empty scaffolding.

---

## 4. Bootstrapping a New Project

Create this structure when starting from scratch:

### `main.py`
```python
import os
from nicegui import app, ui
from components.frame import app_frame
from pages import dashboard, settings
from routers import api, auth
from config import settings as cfg

# ── Middleware ────────────────────────────────────────────────────────────────
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse

PUBLIC_PATHS = {'/login', '/favicon.ico'}

@app.middleware('http')
async def auth_guard(request: Request, call_next):
    if not app.storage.user.get('authenticated') \
            and request.url.path not in PUBLIC_PATHS \
            and not request.url.path.startswith('/_nicegui'):
        return RedirectResponse('/login')
    return await call_next(request)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(api.router)
app.include_router(auth.router)

# ── Static files ──────────────────────────────────────────────────────────────
app.add_static_files('/static', 'static')

# ── Pages ─────────────────────────────────────────────────────────────────────
@ui.page('/')
def home():
    dashboard.page()

@ui.page('/settings')
def settings_page():
    settings.page()

# ── Run ───────────────────────────────────────────────────────────────────────
ui.run(
    title=cfg.APP_TITLE,
    host='0.0.0.0',
    port=cfg.PORT,
    storage_secret=cfg.STORAGE_SECRET,
    reload=cfg.DEBUG,
    dark=None,
    favicon=cfg.FAVICON,
)
```

### `config.py`
```python
import os
from dotenv import load_dotenv

load_dotenv()

APP_TITLE   = os.getenv('APP_TITLE', 'My App')
PORT        = int(os.getenv('PORT', '8080'))
STORAGE_SECRET = os.getenv('STORAGE_SECRET', 'change-me-in-production')
DEBUG       = os.getenv('DEBUG', 'false').lower() == 'true'
FAVICON     = os.getenv('FAVICON', '🚀')
DB_URL      = os.getenv('DB_URL', 'sqlite://data.db')
```

### `.env.example`
```env
APP_TITLE=My App
PORT=8080
STORAGE_SECRET=change-me-in-production
DEBUG=false
FAVICON=🚀
DB_URL=sqlite://data.db
```

### `components/frame.py`
```python
from contextlib import contextmanager
from nicegui import app, ui

# ── Color palette ─────────────────────────────────────────────────────────────
# Call once at module level — takes effect app-wide
ui.colors(
    primary='#1565C0',
    secondary='#00897B',
    accent='#F57C00',
    positive='#2E7D32',
    negative='#C62828',
)

NAV_ITEMS: list[tuple[str, str, str]] = [
    # (route, icon, label)
    ('/',          'dashboard', 'Dashboard'),
    ('/settings',  'settings',  'Settings'),
]


@contextmanager
def app_frame(title: str = '', active: str = '/'):
    """
    Main page shell. Usage:

        @ui.page('/')
        def home():
            with app_frame('Dashboard', active='/'):
                ui.label('Content here')
    """
    dark = ui.dark_mode()
    if app.storage.user.get('dark_mode'):
        dark.enable()

    with ui.header(elevated=True).classes(
        'bg-primary text-white items-center px-6 h-14 gap-3'
    ):
        ui.button(
            icon='menu',
            on_click=lambda: drawer.toggle(),
        ).props('flat round color=white')
        ui.label('AppName').classes('text-xl font-bold flex-1')
        ui.label(
            app.storage.user.get('username', ''),
        ).classes('text-sm opacity-70')
        ui.button(
            icon='logout',
            on_click=lambda: ui.navigate.to('/logout'),
        ).props('flat round color=white').tooltip('Sign out')

    with ui.left_drawer(
        value=False, bottom_corner=True
    ).classes('bg-white border-r') as drawer:
        _nav(active)

    with ui.page_sticky('bottom-right', x_offset=20, y_offset=20):
        pass  # FAB placeholder — add per-page

    with ui.column().classes(
        'w-full max-w-7xl mx-auto px-6 py-8 gap-6'
    ):
        if title:
            ui.label(title).classes('text-3xl font-bold text-grey-9 dark:text-white')
        yield


def _nav(active: str):
    with ui.column().classes('w-full gap-1 pt-2 px-2'):
        ui.label('Navigation').classes(
            'text-xs uppercase tracking-wider text-grey-5 px-2 pb-1'
        )
        for route, icon, label in NAV_ITEMS:
            _nav_item(route, icon, label, active == route)


def _nav_item(route: str, icon: str, label: str, is_active: bool):
    classes = (
        'rounded-lg bg-primary/10 text-primary'
        if is_active
        else 'rounded-lg hover:bg-grey-1 text-grey-8'
    )
    with ui.item(
        on_click=lambda r=route: ui.navigate.to(r)
    ).classes(classes):
        with ui.item_section().props('avatar'):
            ui.icon(icon, color='primary' if is_active else 'grey-7')
        with ui.item_section():
            ui.item_label(label).classes(
                'font-semibold' if is_active else 'font-medium'
            )
```

---

## 5. Integrating Into an Existing Project

### Adding NiceGUI to an existing FastAPI app

```python
# existing_api.py (unchanged)
from fastapi import FastAPI
api = FastAPI()

@api.get('/api/data')
async def get_data():
    return {'items': []}

# main.py (new — wraps existing API)
from nicegui import app as nicegui_app, ui
from existing_api import api   # import existing FastAPI

# Merge: NiceGUI wraps the existing API
# All existing routes stay at /api/* — NiceGUI UI at /
ui.run_with(api, mount_path='/', storage_secret='changeme')

@ui.page('/')
def home():
    ui.label('Dashboard')
```

### Adding pages to an existing NiceGUI project

```python
# existing main.py has ui.run() — add a new page here or in a separate router

# new_router.py
from nicegui import APIRouter, ui

router = APIRouter(prefix='/reports')

@router.page('/')
def reports_home():
    ui.label('Reports')

# In main.py, before ui.run():
from new_router import router
app.include_router(router)
```

---

## 6. Environment & Config Files

### `.env` (never commit — add to `.gitignore`)
```env
STORAGE_SECRET=your-super-secret-key-here
DEBUG=false
PORT=8080
DATABASE_URL=sqlite:///data/app.db
OPENAI_API_KEY=sk-...
```

### Loading in Python
```python
# Using python-dotenv (add to requirements.txt)
from dotenv import load_dotenv
load_dotenv()  # call at top of main.py or config.py

import os
SECRET = os.environ['STORAGE_SECRET']  # fail fast if missing
```

### Key `ui.run()` options
```python
ui.run(
    host='0.0.0.0',          # bind all interfaces (required for Docker)
    port=8080,
    title='App Name',
    storage_secret=SECRET,    # required for app.storage.user persistence
    reload=DEBUG,             # hot reload in dev ONLY — disable in prod
    dark=None,                # None=OS preference, True=dark, False=light
    favicon='🚀',             # or '/static/favicon.ico'
    show=False,               # don't auto-open browser (for servers)
)
```

---

## 7. requirements.txt Baseline

```txt
# Core
nicegui>=2.0.0

# HTTP client (async)
httpx>=0.27.0

# Env loading
python-dotenv>=1.0.0

# Database (choose one)
# tortoise-orm[asyncpg]>=0.21.0   # PostgreSQL
# tortoise-orm[sqlite]>=0.21.0    # SQLite
# sqlalchemy[asyncio]>=2.0.0

# Auth (optional)
# authlib>=1.3.0                  # OAuth2
# PyJWT>=2.8.0                    # JWT

# Testing
# pytest>=8.0.0
# pytest-asyncio>=0.23.0
```

**Install command:**
```bash
pip install -r requirements.txt
# OR with uv (faster):
uv pip install -r requirements.txt
```
