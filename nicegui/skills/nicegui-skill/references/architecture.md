# NiceGUI Architecture & Modularization Reference

## Table of Contents
1. [Page Registration Patterns](#1-page-registration-patterns)
2. [APIRouter — Multi-file Routing](#2-apirouter--multi-file-routing)
3. [Reusable Frame Pattern](#3-reusable-frame-pattern)
4. [sub_pages — Single-Page App Routing](#4-sub_pages--single-page-app-routing)
5. [Multi-Client Synchronization](#5-multi-client-synchronization)
6. [Threaded NiceGUI](#6-threaded-nicegui)
7. [Large App Structure](#7-large-app-structure)

---

## 1. Page Registration Patterns

### Direct decorator (simple)
```python
from nicegui import ui

@ui.page('/')
def home():
    ui.label('Home')

@ui.page('/about')
def about():
    ui.label('About')
```

### Dynamic routes with parameters
```python
@ui.page('/users/{user_id}')
def user_detail(user_id: str):
    user = get_user(user_id)
    if not user:
        ui.label('User not found').classes('text-red-500')
        return
    ui.label(user['name']).classes('text-2xl font-bold')

@ui.page('/items/{item_id}/edit')
def edit_item(item_id: int):  # FastAPI auto-converts types
    item = get_item(item_id)
    form_for(item)

# Query parameters
@ui.page('/search')
def search(q: str = '', page: int = 1, per_page: int = 20):
    results = search_items(q, page=page, per_page=per_page)
    render_results(results)
```

### Function-in-module pattern
```python
# pages/home.py
from nicegui import ui

def content():
    with ui.column().classes('gap-4'):
        ui.label('Home Page').classes('text-2xl font-bold')
        ui.label('Welcome back!')

# pages/about.py
from nicegui import ui

def content():
    ui.label('About us')

# main.py
from nicegui import ui
import pages.home as home_page
import pages.about as about_page

@ui.page('/')
def index():
    home_page.content()

@ui.page('/about')
def about():
    about_page.content()
```

### Class-based (for dependency injection)
```python
class AppPages:
    def __init__(self, db, config):
        self.db = db
        self.config = config
        self._register_pages()

    def _register_pages(self):
        @ui.page('/')
        async def home():
            users = await self.db.fetch_users()
            self.render_home(users)

        @ui.page('/settings')
        def settings():
            self.render_settings()

    def render_home(self, users):
        for u in users:
            ui.label(u['name'])

    def render_settings(self):
        ui.label('Settings')


# Initialize
db = Database()
app_pages = AppPages(db, config)
```

---

## 2. APIRouter — Multi-file Routing

`APIRouter` lets you define pages in separate files and mount them with a prefix:

```python
# routers/admin.py
from nicegui import APIRouter, ui, app

router = APIRouter(prefix='/admin')

@router.page('/')
def admin_dashboard():
    if app.storage.user.get('role') != 'admin':
        ui.navigate.to('/')
        return
    ui.label('Admin Dashboard').classes('text-2xl font-bold')

@router.page('/users')
async def admin_users():
    users = await fetch_all_users()
    for u in users:
        ui.label(u['name'])

@router.page('/users/{user_id}')
async def admin_user(user_id: str):
    user = await fetch_user(user_id)
    ui.label(user['name'])
```

```python
# routers/api.py — REST API routes on the same router
from nicegui import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix='/api/v1')

@router.get('/status')
async def status():
    return {'status': 'ok', 'version': '1.0'}

@router.get('/users')
async def list_users():
    return await fetch_users()
```

```python
# main.py
from nicegui import app, ui
from routers import admin, api

# Mount routers
app.include_router(admin.router)
app.include_router(api.router)

@ui.page('/')
def index():
    ui.label('Main app')

ui.run(storage_secret='changeme')
```

---

## 3. Reusable Frame Pattern

Use Python's `contextmanager` to build shared page shells:

```python
# components/frame.py
from contextlib import contextmanager
from nicegui import app, ui

NAV_ITEMS = [
    ('/', 'home', 'Dashboard'),
    ('/data', 'table_chart', 'Data'),
    ('/settings', 'settings', 'Settings'),
]


@contextmanager
def app_frame(title: str = '', active_route: str = ''):
    """Shared app frame with header, drawer, and main content area."""
    ui.colors(primary='#1565C0')

    # Apply dark mode from user preference
    dark = ui.dark_mode()
    if app.storage.user.get('dark_mode'):
        dark.enable()

    with ui.header(elevated=True).classes('bg-primary text-white items-center px-6 h-14 gap-4'):
        with ui.button(icon='menu', on_click=lambda: drawer.toggle()).props('flat round color=white'):
            pass
        ui.label('MyApp').classes('text-xl font-bold')
        if title:
            ui.label(f'/ {title}').classes('text-white/70')
        ui.space()
        ui.label(app.storage.user.get('username', '')).classes('text-sm')
        ui.button(icon='logout', on_click=lambda: ui.navigate.to('/logout')).props('flat round color=white')

    with ui.left_drawer(value=False, bottom_corner=True).classes('bg-white border-r') as drawer:
        ui.label('Navigation').classes('text-caption text-grey-6 uppercase px-4 pt-4 pb-2')
        for route, icon, label in NAV_ITEMS:
            is_active = active_route == route
            with ui.item(
                on_click=lambda r=route: ui.navigate.to(r)
            ).classes(
                'rounded-lg mx-2 ' + ('bg-primary/10 text-primary' if is_active else 'hover:bg-grey-1')
            ):
                with ui.item_section().props('avatar'):
                    ui.icon(icon, color='primary' if is_active else 'grey-6')
                with ui.item_section():
                    ui.item_label(label).classes('font-medium' if is_active else '')

    with ui.column().classes('w-full max-w-7xl mx-auto px-6 py-8 gap-6'):
        if title:
            ui.label(title).classes('text-3xl font-bold text-grey-9 dark:text-white')
        yield  # <-- page content goes here
```

```python
# pages/dashboard.py
from components.frame import app_frame
from nicegui import ui

def page():
    with app_frame(title='Dashboard', active_route='/'):
        with ui.grid(columns=3).classes('w-full gap-4'):
            for metric in get_metrics():
                with ui.card().classes('p-4'):
                    ui.label(metric['label']).classes('text-sm text-grey-6')
                    ui.label(metric['value']).classes('text-3xl font-bold text-primary')
```

---

## 4. sub_pages — Single-Page App Routing

`ui.sub_pages` enables client-side routing without full page reloads:

```python
from nicegui import ui
from nicegui.page import sub_pages as SubPages

# Define route handlers
def home_view():
    ui.label('Home').classes('text-2xl font-bold')
    ui.link('Go to About', '/about')

def about_view():
    ui.label('About Us').classes('text-2xl font-bold')
    ui.link('Back', '/')

def users_view():
    ui.label('Users List').classes('text-2xl font-bold')

def user_detail_view(user_id: str):
    ui.label(f'User #{user_id}').classes('text-2xl font-bold')


@ui.page('/{_:path}')
def spa():
    with ui.header().classes('bg-primary text-white'):
        ui.link('Home', '/').classes('text-white no-underline')
        ui.link('About', '/about').classes('text-white no-underline ml-4')

    # Register client-side routes
    with SubPages() as pages:
        pages.route('/', home_view)
        pages.route('/about', about_view)
        pages.route('/users', users_view)
        pages.route('/users/{user_id}', user_detail_view)
        pages.not_found(lambda: ui.label('404 - Page not found').classes('text-2xl text-red-500'))
```

### Custom sub_pages with auth
```python
class AuthPages(SubPages):
    PROTECTED = {'/dashboard', '/profile', '/settings'}

    def _render_page(self, match):
        if match.full_url in self.PROTECTED and not app.storage.user.get('authenticated'):
            self._login_wall(match.full_url)
            return True
        return super()._render_page(match)

    def _render_404(self):
        with ui.column().classes('absolute-center items-center gap-4'):
            ui.label('404').classes('text-8xl font-black text-grey-3')
            ui.label('Page not found').classes('text-xl text-grey-6')
            ui.button('Go Home', on_click=lambda: ui.navigate.to('/')).props('color=primary')

    def _login_wall(self, redirect_to: str):
        with ui.card().classes('absolute-center w-96 p-8'):
            ui.label('Login Required').classes('text-xl font-bold mb-4')
            username = ui.input('Username').classes('w-full')
            password = ui.input('Password').props('type=password').classes('w-full')

            def login():
                if authenticate(username.value, password.value):
                    app.storage.user['authenticated'] = True
                    ui.navigate.to(redirect_to)

            ui.button('Login', on_click=login).classes('w-full mt-4').props('color=primary')
```

---

## 5. Multi-Client Synchronization

### Event[T] — broadcast to all connected clients

```python
from nicegui.events import Event

# Typed event broadcasts
class AppEvents:
    new_order = Event[dict]()
    user_joined = Event[str]()
    system_alert = Event[dict]()
    data_refresh = Event()

events = AppEvents()

# In a background task or API endpoint
@app.post('/api/orders')
async def create_order(order: dict):
    saved = await save_order_to_db(order)
    events.new_order.emit(saved)  # broadcasts to all UIs
    return saved

# In each page
@ui.page('/orders')
def orders_page():
    order_list_container = ui.column().classes('w-full gap-2')
    notification_badge = ui.badge('0', color='red')
    new_count = {'n': 0}

    @ui.refreshable
    def order_list():
        orders = get_all_orders()
        for order in orders:
            with order_list_container:
                order_card(order)

    @events.new_order.subscribe
    def on_new_order(order: dict):
        new_count['n'] += 1
        notification_badge.text = str(new_count['n'])
        order_list.refresh()
        ui.notify(f'New order: #{order["id"]}', type='info', position='top-right')

    order_list()
```

### Shared mutable state (with refresh)
```python
from dataclasses import dataclass, field
from nicegui.events import Event

@dataclass
class AppState:
    connected_users: list[str] = field(default_factory=list)
    messages: list[dict] = field(default_factory=list)

state = AppState()
state_changed = Event()

@ui.page('/')
async def index():
    username = app.storage.user.get('username', f'User-{id(ui.context.client)[:4]}')
    state.connected_users.append(username)
    state_changed.emit()

    @ui.refreshable
    def user_list():
        for user in state.connected_users:
            ui.chip(user, icon='person')

    user_list()

    @state_changed.subscribe
    def refresh():
        user_list.refresh()

    await ui.context.client.disconnected()
    state.connected_users.remove(username)
    state_changed.emit()
```

---

## 6. Threaded NiceGUI

Run NiceGUI in a thread from a non-async application:

```python
import threading
from nicegui import ui, app
from nicegui.events import Event

class NiceGUIApp:
    """Embeds NiceGUI in a thread for non-async apps."""

    def __init__(self):
        self.status_update = Event[str]()
        self.data_update = Event[dict]()
        self._started = threading.Event()

    def start(self, host='localhost', port=8080):
        """Start NiceGUI in a background thread."""
        app.on_startup(self._started.set)
        thread = threading.Thread(
            target=lambda: ui.run(
                self.root,
                host=host,
                port=port,
                reload=False,
                show=False,
                title='My App',
            ),
            daemon=True,
        )
        thread.start()
        self._started.wait(timeout=5.0)
        print(f'UI available at http://{host}:{port}')

    def root(self):
        """Define the UI."""
        status_label = ui.label('Idle').classes('text-lg')
        data_display = ui.json_editor({'content': {'json': {}}}).classes('w-full')

        @self.status_update.subscribe
        def on_status(msg: str):
            status_label.text = msg

        @self.data_update.subscribe
        def on_data(data: dict):
            # Update JSON editor
            pass

    def update_status(self, msg: str):
        """Call from main thread."""
        self.status_update.emit(msg)

    def push_data(self, data: dict):
        """Push data to all connected UIs."""
        self.data_update.emit(data)


# Usage (from non-async context)
gui = NiceGUIApp()
gui.start()

# Now drive the UI from your main program
import time
for i in range(10):
    gui.update_status(f'Processing step {i+1}/10...')
    time.sleep(1)

gui.update_status('Done!')
```

---

## 7. Large App Structure

Recommended directory layout for production apps:

```
my_app/
├── main.py                  # ui.run() entry point
├── config.py                # Settings, environment vars
├── models.py                # Database models (Tortoise/SQLAlchemy)
│
├── routers/                 # APIRouter modules
│   ├── __init__.py
│   ├── admin.py             # /admin/* routes
│   ├── api.py               # /api/* REST endpoints
│   └── auth.py              # /login, /logout, /oauth
│
├── pages/                   # Page content functions
│   ├── __init__.py
│   ├── dashboard.py
│   ├── users.py
│   └── settings.py
│
├── components/              # Reusable UI components
│   ├── __init__.py
│   ├── frame.py             # app_frame context manager
│   ├── cards.py             # MetricCard, StatusCard, etc.
│   ├── tables.py            # Reusable table components
│   └── forms.py             # Reusable forms
│
├── state.py                 # Shared Event[T] instances + AppState
├── middleware.py            # Auth middleware
│
├── static/                  # Static files (CSS, images)
│   └── custom.css
│
└── tests/                   # Test files
    ├── conftest.py
    └── test_pages.py
```

```python
# main.py
from nicegui import app, ui
from config import settings
from middleware import auth_middleware
from routers import admin, api, auth

# Register middleware
app.add_middleware(auth_middleware)

# Mount routers
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(api.router)

# Static files
app.add_static_files('/static', 'static')

# Main page
@ui.page('/')
def index():
    from pages.dashboard import page
    page()

ui.run(
    title='My App',
    host='0.0.0.0',
    port=8080,
    storage_secret=settings.storage_secret,
    reload=settings.debug,
    dark=None,
)
```
