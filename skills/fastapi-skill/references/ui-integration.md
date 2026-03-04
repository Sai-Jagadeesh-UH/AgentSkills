# UI Integration Reference — NiceGUI & Jinja2

## Table of Contents
1. [NiceGUI Integration](#nicegui)
2. [Jinja2 Templates](#jinja2)
3. [HTMX with FastAPI](#htmx)
4. [Static Files](#static-files)
5. [Shared Pydantic Models](#shared-models)

---

## NiceGUI Integration {#nicegui}

NiceGUI provides a Python-based UI layer that can run alongside or integrated into FastAPI.

```bash
pip install nicegui
```

### Pattern 1: Integrated (same process, same port)

```python
# app/main.py
from fastapi import FastAPI
from nicegui import ui, app as nicegui_app

fastapi_app = FastAPI()

# Mount your FastAPI routers
fastapi_app.include_router(api_router, prefix="/api")

# Define NiceGUI pages
@ui.page("/")
async def index():
    with ui.column().classes("items-center"):
        ui.label("Welcome to My App").classes("text-3xl font-bold")
        ui.button("View Items", on_click=lambda: ui.navigate.to("/items"))

@ui.page("/items")
async def items_page():
    with ui.column():
        ui.label("Items").classes("text-2xl")
        # Fetch from your own API
        result = await fetch_items()
        for item in result:
            ui.label(f"{item['name']}: ${item['price']}")

# CRITICAL: run NiceGUI with FastAPI app
ui.run_with(
    fastapi_app,
    mount_path="/",       # NiceGUI serves at root
    storage_secret="your-secret",
    title="My App",
    favicon="🚀",
)

# Run: uvicorn app.main:fastapi_app --reload
```

### Pattern 2: Separate Processes (recommended for complex apps)

```python
# Run FastAPI and NiceGUI on different ports
# FastAPI: port 8000 (API only)
# NiceGUI: port 3000 (UI only, calls API via httpx)

# ui/main.py
from nicegui import ui
import httpx

API_BASE = "http://localhost:8000/api/v1"
client = httpx.AsyncClient(base_url=API_BASE)

@ui.page("/")
async def dashboard():
    # Fetch from FastAPI backend
    response = await client.get("/stats")
    stats = response.json()

    with ui.row():
        ui.number("Total Users").bind_value_from(stats, "total_users")
        ui.number("Active Orders").bind_value_from(stats, "active_orders")

ui.run(port=3000, title="Dashboard")
```

### NiceGUI Auth Integration

```python
# Use NiceGUI's storage for session management
from nicegui import ui, app

@ui.page("/login")
async def login_page():
    username = ui.input("Username")
    password = ui.input("Password", password=True)

    async def do_login():
        response = await client.post("/auth/token", data={
            "username": username.value,
            "password": password.value,
        })
        if response.status_code == 200:
            token = response.json()["access_token"]
            app.storage.user["token"] = token  # persisted in browser
            ui.navigate.to("/dashboard")
        else:
            ui.notify("Invalid credentials", type="negative")

    ui.button("Login", on_click=do_login)

@ui.page("/dashboard")
async def dashboard():
    token = app.storage.user.get("token")
    if not token:
        return ui.navigate.to("/login")

    # Use token for API calls
    headers = {"Authorization": f"Bearer {token}"}
    response = await client.get("/me", headers=headers)
    user = response.json()
    ui.label(f"Hello, {user['full_name']}!")
```

### Sharing Pydantic Models with NiceGUI

```python
# schemas/user.py (shared between API and UI)
from pydantic import BaseModel

class UserRead(BaseModel):
    id: str
    email: str
    full_name: str

# In UI
from app.schemas.user import UserRead
import httpx

async def get_current_user(token: str) -> UserRead:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "http://localhost:8000/api/v1/users/me",
            headers={"Authorization": f"Bearer {token}"}
        )
    return UserRead.model_validate(response.json())
```

---

## Jinja2 Templates {#jinja2}

### Setup

```bash
pip install jinja2 python-multipart
```

```python
# app/main.py
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

app = FastAPI()

# Static files
app.mount("/static", StaticFiles(directory="app/ui/static"), name="static")

# Templates
templates = Jinja2Templates(directory="app/ui/templates")
```

### Directory Structure

```
app/ui/
├── templates/
│   ├── base.html          ← base template with layout
│   ├── index.html
│   ├── users/
│   │   ├── list.html
│   │   └── detail.html
│   └── components/
│       ├── nav.html
│       └── pagination.html
└── static/
    ├── css/
    │   └── app.css
    └── js/
        └── app.js
```

### Base Template

```html
<!-- app/ui/templates/base.html -->
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}My API{% endblock %}</title>
    <link rel="stylesheet" href="{{ url_for('static', path='css/app.css') }}">
    {% block head %}{% endblock %}
</head>
<body>
    <nav>{% include "components/nav.html" %}</nav>
    <main>{% block content %}{% endblock %}</main>
    <script src="{{ url_for('static', path='js/app.js') }}"></script>
    {% block scripts %}{% endblock %}
</body>
</html>
```

### Template Routes

```python
# app/api/pages.py — template-returning endpoints
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["pages"])

@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "title": "Home"}
    )

@router.get("/users", response_class=HTMLResponse)
async def users_page(
    request: Request,
    page: int = 1,
    db: AsyncSession = Depends(get_db),
):
    users, total = await user_repo.list_paginated(offset=(page-1)*20, limit=20)
    return templates.TemplateResponse("users/list.html", {
        "request": request,
        "users": users,
        "total": total,
        "page": page,
        "pages": (total + 19) // 20,
    })
```

### Custom Jinja2 Filters and Globals

```python
from datetime import datetime

def format_datetime(value: datetime, fmt: str = "%Y-%m-%d %H:%M") -> str:
    return value.strftime(fmt) if value else ""

def currency(value: float, symbol: str = "$") -> str:
    return f"{symbol}{value:,.2f}"

templates.env.filters["datetime"] = format_datetime
templates.env.filters["currency"] = currency
templates.env.globals["app_name"] = settings.app_name
```

---

## HTMX with FastAPI {#htmx}

HTMX allows dynamic updates without a full SPA, keeping templates server-side.

```html
<!-- In base.html -->
<script src="https://unpkg.com/htmx.org@1.9.10"></script>
```

### HTMX Pattern — Partial Template Updates

```python
# app/api/pages.py
from fastapi.responses import HTMLResponse

@router.get("/users/search", response_class=HTMLResponse)
async def search_users(
    request: Request,
    q: str = "",
    db: AsyncSession = Depends(get_db),
):
    """Returns only the table rows fragment for HTMX to swap"""
    users = await user_repo.search(q) if q else []
    return templates.TemplateResponse(
        "users/partials/rows.html",  # just the <tbody> rows
        {"request": request, "users": users}
    )
```

```html
<!-- templates/users/list.html -->
<input
    type="search"
    name="q"
    hx-get="/users/search"
    hx-trigger="input changed delay:300ms"
    hx-target="#users-table-body"
    hx-swap="innerHTML"
    placeholder="Search users..."
>

<table>
    <tbody id="users-table-body">
        {% include "users/partials/rows.html" %}
    </tbody>
</table>
```

```html
<!-- templates/users/partials/rows.html -->
{% for user in users %}
<tr>
    <td>{{ user.full_name }}</td>
    <td>{{ user.email }}</td>
    <td>{{ user.created_at | datetime }}</td>
</tr>
{% else %}
<tr><td colspan="3">No users found</td></tr>
{% endfor %}
```

### HTMX Form Submit

```html
<!-- Create user form with HTMX -->
<form
    hx-post="/users"
    hx-target="#user-list"
    hx-swap="afterbegin"
    hx-on::after-request="this.reset()"
>
    <input name="email" type="email" required>
    <input name="full_name" required>
    <button type="submit">Create User</button>
</form>
```

```python
@router.post("/users", response_class=HTMLResponse, status_code=201)
async def create_user_htmx(
    request: Request,
    email: str = Form(...),
    full_name: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    user = await user_service.create(db, UserCreate(email=email, full_name=full_name))
    # Return just the new row for HTMX to insert
    return templates.TemplateResponse(
        "users/partials/row.html",
        {"request": request, "user": user},
    )
```

---

## Static Files {#static-files}

```python
from fastapi.staticfiles import StaticFiles

# Mount at /static path
app.mount("/static", StaticFiles(directory="app/ui/static"), name="static")

# URL generation in templates: {{ url_for('static', path='/css/app.css') }}
# URL generation in Python: request.url_for('static', path='/css/app.css')
```

### Static Files Structure

```
app/ui/static/
├── css/
│   ├── app.css
│   └── tailwind.css    # if using Tailwind CDN
├── js/
│   ├── app.js
│   └── htmx.min.js     # or use CDN
├── images/
│   └── logo.svg
└── favicon.ico
```

---

## Shared Pydantic Models {#shared-models}

When using NiceGUI or Jinja2 in the same codebase, share Pydantic schemas:

```python
# schemas/user.py — shared between API endpoints and UI layers
from pydantic import BaseModel, EmailStr

class UserRead(BaseModel):
    """Used as API response model AND in templates"""
    id: str
    email: EmailStr
    full_name: str
    role: str

    @property
    def display_name(self) -> str:
        return self.full_name or self.email.split("@")[0]

    @property
    def avatar_url(self) -> str:
        import hashlib
        email_hash = hashlib.md5(self.email.lower().encode()).hexdigest()
        return f"https://www.gravatar.com/avatar/{email_hash}?s=40&d=identicon"
```

```html
<!-- Use in Jinja2 templates — methods and properties work! -->
<img src="{{ user.avatar_url }}" alt="{{ user.display_name }}">
<span>{{ user.display_name }}</span>
```
