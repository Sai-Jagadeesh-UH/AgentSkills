# NiceGUI Internals — Routing, App Startup & Configuration

> Load when: debugging page routing issues, using sub_pages, injecting route parameters, mounting on FastAPI, customizing startup/shutdown, diagnosing 404s, understanding `ui.run()` parameters, using `APIRouter`.

## Table of Contents
1. [Page Decorator Internals](#1-page-decorator-internals)
2. [Route Registration Lifecycle](#2-route-registration-lifecycle)
3. [PageArguments — Injecting Route Params](#3-pagearguments--injecting-route-params)
4. [Sub-Pages — Client-Side Navigation](#4-sub-pages--client-side-navigation)
5. [APIRouter](#5-apirouter)
6. [App Startup & Shutdown Sequence](#6-app-startup--shutdown-sequence)
7. [ui.run() Parameters Reference](#7-uirun-parameters-reference)
8. [ui.run_with() — Mounting on FastAPI](#8-uirun_with--mounting-on-fastapi)
9. [Patterns & Recipes](#9-patterns--recipes)

---

## 1. Page Decorator Internals

`@ui.page('/path')` is implemented as a class `page` in `page.py`:

```python
class page:
    def __init__(
        self,
        path: str,
        *,
        title: str | None = None,
        viewport: str | None = None,
        favicon: str | None = None,
        dark: bool | None = ...,  # ... = use app default
        language: str | None = None,
        response_timeout: float = 3.0,
        reconnect_timeout: float = ...,  # ... = use app default
        api_router: APIRouter | None = None,
        kwargs...
    )
```

### What `@ui.page` does on decoration

```python
# page.py __call__
def __call__(self, func: Callable) -> Callable:
    # Validates sub_pages if provided
    self._validate_sub_pages()
    # Registers GET route on FastAPI (or the provided api_router)
    parameters = inspect.signature(func).parameters
    optional_types = self._get_optional_types(parameters)
    # Build the FastAPI GET handler
    async def route_handler(**kwargs):
        ...
    core.app.get(self.path, **self.kwargs)(route_handler)
    return func
```

### The route handler — what runs on each page request

```python
async def route_handler(**kwargs):
    # 1. Create a new Client for this request
    client = Client(self, request=request)

    # 2. Call the user's page function inside a client context
    with client:
        # Sync functions run directly
        if not asyncio.iscoroutinefunction(func):
            result = func(**kwargs)
        else:
            # Async functions run as background task
            task = background_tasks.create(func(**kwargs))
            # Wait for either task completion OR client.connected()
            done, _ = await asyncio.wait(
                [task, asyncio.create_task(client.connected())],
                timeout=response_timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )
            # response_timeout exceeded → page is served as-is (partial)

    # 3. Build and return HTTP response
    return client.build_response(request, **page_args)
```

**Key insight:** For async page functions, NiceGUI serves the response when EITHER the function completes OR `response_timeout` expires (default 3s). This allows async pages to load quickly while data fetches happen in the background after the WebSocket connects.

### response_timeout behavior

```python
# If async page function completes within response_timeout:
# → Full initial UI sent in first HTTP response

# If response_timeout expires first:
# → Partial UI (whatever ran synchronously) sent
# → Async operations continue, updates arrive via WebSocket

# Increase for slow startup pages:
@ui.page('/heavy', response_timeout=10.0)
async def heavy_page():
    data = await load_large_dataset()  # up to 10s allowed
    ui.chart(data)
```

---

## 2. Route Registration Lifecycle

```
@ui.page('/path') applied
  ↓
page.__call__(func) invoked (at import time / module load)
  ↓
FastAPI GET route registered: core.app.get('/path', ...)(route_handler)
  ↓
  [At runtime — browser requests /path]
  ↓
FastAPI dispatches to route_handler(request, **path_params)
  ↓
Client created → page function called → build_response()
  ↓
HTTP 200 with full HTML + embedded element JSON
  ↓
Browser establishes WebSocket → handshake → client.connected() sets
```

### Auto-index page

```python
# NiceGUI creates an index page from @ui.page('/') automatically
# If no @ui.page('/') defined, serves the auto-index

# In nicegui.py _startup():
if '/' not in [p.path for p in pages]:
    # register empty index
```

### 404 / exception handlers

```python
# Custom 404:
@app.exception_handler(404)
async def not_found(request, exc):
    return responses.RedirectResponse('/404')

# Global error page:
app.add_exception_handler(Exception, my_handler)
```

---

## 3. PageArguments — Injecting Route Params

When a page builder is called via sub_pages, it receives a `PageArguments` object:

```python
# page_arguments.py
@dataclass
class RouteMatch:
    path: str           # matched path segment
    params: dict        # path parameters extracted
    query: dict         # query string parameters

@dataclass
class PageArguments:
    matches: list[RouteMatch]   # all matched route segments

    # Convenience: access first match
    @property
    def params(self) -> dict: return self.matches[-1].params
    @property
    def query(self) -> dict:  return self.matches[-1].query
```

### build_kwargs() — FastAPI injection

```python
# page_arguments.py build_kwargs()
def build_kwargs(func: Callable, route_match: RouteMatch, request: Request) -> dict:
    """Inspects function signature, injects matching params by name."""
    sig = inspect.signature(func)
    kwargs = {}
    for name, param in sig.parameters.items():
        if name == 'request':
            kwargs[name] = request
        elif name in route_match.params:
            kwargs[name] = route_match.params[name]
        elif name in route_match.query:
            kwargs[name] = route_match.query[name]
    return kwargs
```

### Path parameters

```python
@ui.page('/user/{user_id}')
def user_page(user_id: str):
    ui.label(f'User: {user_id}')

# Query params via Request:
@ui.page('/search')
async def search(request: Request):
    q = request.query_params.get('q', '')
    ui.label(f'Search: {q}')
```

---

## 4. Sub-Pages — Client-Side Navigation

`sub_pages` enables client-side navigation (no full page reload) by swapping content within a container:

```python
# page.py / sub_pages_router.py
@ui.page('/')
def index():
    with ui.row():
        ui.link('Home', '/app/home')
        ui.link('Settings', '/app/settings')

    # Sub-pages container — content swaps on navigate
    ui.sub_pages({
        '/app/home': home_builder,
        '/app/settings': settings_builder,
    }, default='/app/home')

def home_builder():
    ui.label('Home page content')

def settings_builder():
    ui.label('Settings content')
```

### SubPagesRouter internals

```python
# sub_pages_router.py SubPagesRouter
class SubPagesRouter(Element, component='sub_pages_router.js'):
    def __init__(self, routes: dict[str, Callable], default: str | None = None):
        super().__init__()
        # Registers JS component that listens for navigation events
        # Browser-side: intercepts <a> clicks → emits 'navigate' event
        # On navigate: old content deleted, new builder called
```

### Navigation events flow

```python
# Browser clicks link → JS intercepts → emits to server
# server: _handle_navigate(path)
#   → finds matching builder from routes
#   → clears old content from container
#   → calls new builder (creates elements in container)
#   → browser updates URL via history.pushState() (no reload)

# Programmatic navigation:
ui.navigate.to('/app/settings')        # full page navigate
ui.navigate.to('/app/settings', new_tab=True)

# Within sub_pages context: update URL without server round-trip
# (handled by JS on the client side)
```

### Route matching

```python
# Can_resolve check (for back/forward navigation):
# sub_pages_router._can_resolve_full_path(path)
# → tries each pattern in order (supports path params: /user/{id})
# → returns True if any pattern matches
```

---

## 5. APIRouter

NiceGUI's `APIRouter` extends FastAPI's `APIRouter` with `.page()`:

```python
# api_router.py
from nicegui import APIRouter

router = APIRouter(prefix='/admin')

@router.page('/dashboard')
def admin_dashboard():
    ui.label('Admin Dashboard')

@router.get('/api/stats')
async def get_stats():
    return {'users': 42}

# Mount in main app:
app.include_router(router)
```

### All standard FastAPI methods available

```python
router.get('/path', ...)
router.post('/path', ...)
router.put('/path', ...)
router.delete('/path', ...)
router.page('/path', ...)    # NiceGUI addition
```

### Prefix and tags

```python
router = APIRouter(prefix='/api/v1', tags=['v1'])

# All routes: /api/v1/...
# All tagged: 'v1' in OpenAPI docs
```

---

## 6. App Startup & Shutdown Sequence

### Startup (nicegui.py `_startup()`)

```python
async def _startup() -> None:
    # 1. Start background services
    await storage.backup.start()         # persistent storage sync
    background_tasks.create(outbox_loop) # global outbox

    # 2. Set WebSocket keepalive timers
    sio.eio.ping_interval = max(reconnect_timeout * 0.8, 4)
    sio.eio.ping_timeout  = max(reconnect_timeout * 0.4, 2)

    # 3. Register pruning tasks (every 10s)
    #    - Client.prune_instances(age_threshold=60.0)
    #    - storage.prune_tab_storage()
    #    - storage.prune_browser_storage()

    # 4. Start binding refresh loop
    background_tasks.create(binding.refresh_loop())

    # 5. Invoke user startup handlers
    for handler in app._startup_handlers:
        await handler() if asyncio.iscoroutinefunction(handler) else handler()

    # 6. Register / start socket.io
    sio.on('connect',    _on_connect)
    sio.on('handshake',  _on_handshake)
    sio.on('disconnect', _on_disconnect)
    sio.on('event',      _on_event)
    sio.on('ack',        _on_ack)
    sio.on('javascript_response', _on_javascript_response)
```

### Shutdown

```python
async def _shutdown() -> None:
    # 1. User shutdown handlers
    for handler in app._shutdown_handlers:
        await handler()

    # 2. Await tasks registered with await_on_shutdown
    await background_tasks.teardown()

    # 3. Flush persistent storage
    await storage.backup.stop()
```

### app.on_startup / app.on_shutdown

```python
@app.on_startup
async def startup():
    # Connect to database, warm caches, etc.
    await db.connect()

@app.on_shutdown
async def shutdown():
    await db.disconnect()
```

---

## 7. ui.run() Parameters Reference

```python
ui.run(
    # Server
    host='0.0.0.0',          # bind host
    port=8080,                # bind port
    reload=True,              # auto-reload on file change (dev only)
    show=True,                # open browser on startup

    # TLS
    ssl_certfile=None,        # path to SSL cert
    ssl_keyfile=None,         # path to SSL key

    # App metadata
    title='NiceGUI',
    favicon=None,             # path or URL to .ico/.png
    dark=None,                # None = system, True = dark, False = light
    language='en-US',         # Quasar language pack

    # Storage
    storage_secret=None,      # required for app.storage.user

    # Reconnect behavior
    reconnect_timeout=3.0,    # seconds to wait before deleting disconnected client

    # Binding
    binding_refresh_interval=0.1,  # poll interval for active_links (None = disable)

    # Performance
    message_history_length=1000,  # max messages kept for reconnect rewind

    # Air (remote access)
    on_air=None,              # True or token string for NiceGUI On Air relay

    # UVICORN options (passed through)
    uvicorn_logging_level='warning',
    uvicorn_reload_dirs=None,
    uvicorn_reload_includes=['*.py'],
    uvicorn_reload_excludes=['.*, .py[cod], .sw.*'],

    # Quasar
    tailwind=True,            # include Tailwind CSS
    quasar_config={},         # extra Quasar config (e.g. brand colors)

    # Prod
    endpoint_documentation='none',  # 'none'|'internal'|'page'|'all'
)
```

### Key parameter notes

```python
# storage_secret: any string, used to sign session cookie
# Without it: app.storage.user raises RuntimeError
ui.run(storage_secret='my-secret-key-change-in-prod')

# reconnect_timeout: after disconnect, how long before client.delete()
# Increase for mobile users on flaky connections:
ui.run(reconnect_timeout=30.0)

# binding_refresh_interval: reduce CPU for apps with many plain-dict bindings
# Set to None if all bindings use ObservableDict/BindableProperty:
ui.run(binding_refresh_interval=None)

# quasar_config: customize Quasar global config
ui.run(quasar_config={
    'brand': {
        'primary': '#1976D2',
        'secondary': '#26A69A',
    },
    'notify': {'position': 'top'},
})
```

---

## 8. ui.run_with() — Mounting on FastAPI

```python
# ui_run_with.py
from fastapi import FastAPI
from nicegui import ui, app as nicegui_app

fastapi_app = FastAPI()

@fastapi_app.get('/api/data')
async def get_data():
    return {'result': 42}

@ui.page('/')
def index():
    ui.label('Hello from NiceGUI')

ui.run_with(
    fastapi_app,
    mount_path='/nicegui',   # default: '/'
    storage_secret='...',
    # ... same params as ui.run() except host/port/reload
)

# Run: uvicorn myapp:fastapi_app --reload
```

### Middleware integration

```python
# NiceGUI adds its middleware to the provided FastAPI app:
# 1. RequestTrackingMiddleware → creates session IDs
# 2. Socket.IO ASGI app mounted at /socket.io
# 3. Static file routes for /_nicegui/...

# Your FastAPI middleware stack still applies to API routes
fastapi_app.add_middleware(CORSMiddleware, ...)
```

### Lifespan events

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    await db.connect()
    yield
    # shutdown
    await db.disconnect()

fastapi_app = FastAPI(lifespan=lifespan)
ui.run_with(fastapi_app)
```

---

## 9. Patterns & Recipes

### Dynamic route with type conversion

```python
@ui.page('/item/{item_id}')
def item_page(item_id: int):   # FastAPI converts str → int
    ui.label(f'Item #{item_id}')
    # item_id is already an int here
```

### Redirect on missing page

```python
@ui.page('/secure')
def secure():
    if not app.storage.user.get('logged_in'):
        ui.navigate.to('/login')
        return        # IMPORTANT: return after navigate
    ui.label('Secure content')
```

### Running startup work after client connects

```python
@ui.page('/')
async def index():
    spinner = ui.spinner()
    await ui.context.client.connected()   # wait for WebSocket
    data = await fetch_data()             # now safe to do async I/O
    spinner.delete()
    ui.label(str(data))
```

### Multiple routers for modular apps

```python
# admin/router.py
from nicegui import APIRouter
router = APIRouter(prefix='/admin')

@router.page('/users')
def users(): ...

# main.py
from admin.router import router as admin_router
from nicegui import app
app.include_router(admin_router)

ui.run()
```

### Page with sub_pages and fallback

```python
@ui.page('/app')
def shell():
    # Persistent nav sidebar
    with ui.left_drawer():
        ui.link('Dashboard', '/app/dashboard')
        ui.link('Settings', '/app/settings')

    # Content area — sub_pages swap content here
    ui.sub_pages({
        '/app/dashboard': build_dashboard,
        '/app/settings':  build_settings,
        '/app/profile/{user_id}': build_profile,
    }, default='/app/dashboard')
```

### Inspecting registered routes

```python
from nicegui import core

for route in core.app.routes:
    print(route.path, route.methods)
```
