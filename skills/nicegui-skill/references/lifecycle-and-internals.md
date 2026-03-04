# NiceGUI Lifecycle & Internals Reference

## Table of Contents
1. [Storage System — 5 Tiers](#1-storage-system--5-tiers)
2. [Client Lifecycle](#2-client-lifecycle)
3. [Page Rendering Model](#3-page-rendering-model)
4. [Multicasting to Clients](#4-multicasting-to-clients)
5. [Reconnect & Timeout Behavior](#5-reconnect--timeout-behavior)
6. [Token & Session Identity](#6-token--session-identity)
7. [Background Tasks & App Lifecycle](#7-background-tasks--app-lifecycle)

---

## 1. Storage System — 5 Tiers

NiceGUI provides five distinct storage scopes. Choose the right tier based on how long and how broadly data must persist.

### Comparison Table

| Feature | `client` | `tab` | `browser` | `user` | `general` |
|---------|----------|-------|-----------|--------|-----------|
| **Location** | Server | Server | Browser cookie | Server | Server |
| **Across tabs** | No | No | Yes | Yes | Yes |
| **Across browsers** | No | No | No | No | Yes |
| **Across server restarts** | No | Yes* | No | Yes | Yes |
| **Across page reloads** | No | Yes | Yes | Yes | Yes |
| **Needs `await client.connected()`** | No | **Yes** | No | No | No |
| **Write only before response** | No | No | **Yes** | No | No |
| **Needs serializable data** | No | No | Yes | Yes | Yes |
| **Needs `storage_secret`** | No | No | Yes | Yes | No |

*Tab storage currently in-memory; server restart clears it.

### `app.storage.client` — Per-page-visit
```python
# Scope: unique per client connection (page visit)
# Lost on: reload, navigation, browser close
# Use: heavy objects, DB connections, per-request caching

@ui.page('/')
def index():
    # Each page visit gets its own isolated dict
    app.storage.client['db'] = create_db_connection()
    # No serialization needed — arbitrary Python objects
```

### `app.storage.tab` — Per-tab session
```python
# Scope: unique per browser tab (persists across reloads of same tab)
# Requires: await client.connected() before accessing
# Use: tab-specific counters, wizard state, local form drafts

@ui.page('/')
async def index():
    await ui.context.client.connected()  # REQUIRED before tab storage
    app.storage.tab['count'] = app.storage.tab.get('count', 0) + 1
    ui.label(f'Tab reloaded {app.storage.tab["count"]} times')
    ui.button('Reload page', on_click=ui.navigate.reload)

ui.run()
```

### `app.storage.user` — Per-browser-session (most useful)
```python
# Scope: associated with browser session cookie ID
# Persists: all tabs + server restarts
# Requires: storage_secret in ui.run()
# Use: user preferences, auth state, persistent settings

@ui.page('/')
def index():
    app.storage.user['visits'] = app.storage.user.get('visits', 0) + 1
    ui.label(f'You visited {app.storage.user["visits"]} times')

ui.run(storage_secret='your-secret-key-here')
```

**Auth pattern with `app.storage.user`:**
```python
# Login handler
def login(username: str, password: str) -> bool:
    if authenticate(username, password):
        app.storage.user.update({
            'authenticated': True,
            'username': username,
            'role': get_role(username),
        })
        return True
    return False

# Middleware guard
@app.middleware('http')
async def auth_guard(request: Request, call_next):
    if not app.storage.user.get('authenticated') \
            and request.url.path not in PUBLIC_PATHS \
            and not request.url.path.startswith('/_nicegui'):
        return RedirectResponse('/login')
    return await call_next(request)
```

### `app.storage.browser` — Browser cookie only
```python
# Scope: browser session (shared across tabs, lost on browser close)
# Requires: storage_secret
# Contains by default: {'id': '<unique_browser_id>'}
# Use: tracking unique browsers (analytics), lightweight client-side flags
# AVOID: prefer app.storage.user — browser storage sends data in every HTTP request

from collections import Counter
counter = Counter()

@ui.page('/')
def index():
    browser_id = app.storage.browser['id']  # always populated
    counter[browser_id] += 1
    ui.label(f'{len(counter)} unique browsers, {sum(counter.values())} total visits')

# NOTE: cannot write to browser storage after initial HTTP response is sent
# All writes must happen synchronously in the page function before any await
```

### `app.storage.general` — App-wide shared state
```python
# Scope: all users, all sessions
# Persists: server restarts (written to disk as JSON)
# Requires: data must be JSON-serializable
# Use: app config, feature flags, global counters, shared resources

# Shared message board
@ui.page('/')
def index():
    messages = app.storage.general.get('messages', [])
    for msg in messages:
        ui.label(msg)

    def post(text: str):
        msgs = app.storage.general.setdefault('messages', [])
        msgs.append(text)
        app.storage.general['messages'] = msgs  # trigger persistence

    ui.input(on_change=lambda e: post(e.value))
```

### Max Tab Storage Age
```python
from datetime import timedelta
from nicegui import app

# Default: 30 days. Reduce for memory-sensitive apps.
app.storage.max_tab_storage_age = timedelta(hours=2).total_seconds()
```

---

## 2. Client Lifecycle

Every browser tab connecting to a NiceGUI page creates a **client** object with its own lifecycle.

### Lifecycle Sequence
```
Browser opens page
       ↓
HTTP GET → server calls @ui.page function (builds initial DOM)
       ↓
HTML response sent → browser renders initial skeleton
       ↓
WebSocket connects
       ↓
await ui.context.client.connected()  ← unblocks here
       ↓
NiceGUI patches DOM over WebSocket
       ↓
User interacts → events fire → handlers run → DOM patched
       ↓
Browser navigates away / closes tab
       ↓
await ui.context.client.disconnected()  ← unblocks here
       ↓
Client cleaned up
```

### Key Client Methods
```python
@ui.page('/')
async def index():
    # 1. Build initial UI (synchronously or with fast async ops)
    label = ui.label('Connecting...')
    spinner = ui.spinner()

    # 2. Wait for WebSocket
    await ui.context.client.connected()

    # 3. Now safe to: run JS, access app.storage.tab, do slow I/O
    label.text = 'Connected!'
    spinner.visible = False

    data = await load_data()    # slow DB fetch after UI is shown
    render_data(data)

    # 4. Wait for disconnect to clean up
    await ui.context.client.disconnected()
    cleanup_resources()         # close connections, cancel tasks
```

### Accessing the Current Client
```python
from nicegui import ui

@ui.page('/')
def index():
    # Current client accessible via context
    client = ui.context.client
    print(f'Client ID: {client.id}')

# Or as a page function parameter
@ui.page('/')
def index(client):
    print(f'Client ID: {client.id}')
```

### Running JavaScript Requires Connected Client
```python
@ui.page('/')
async def index():
    # ui.run_javascript() needs active WebSocket
    await ui.context.client.connected()
    result = await ui.run_javascript('return document.title')
    ui.label(f'Page title: {result}')
```

---

## 3. Page Rendering Model

### Per-Client Isolation
Every `@ui.page` call creates **independent UI trees per client** — unlike traditional server-side rendering where all users share one page state.

```python
# IMPORTANT: these variables are NOT shared between clients
@ui.page('/')
def index():
    count = 0  # local to this function call — each client gets their own

    def increment():
        nonlocal count
        count += 1
        label.text = str(count)

    label = ui.label('0')
    ui.button('Increment', on_click=increment)
```

### Response Timeout
NiceGUI gives the page function a limited time to build and send the initial HTML:

```python
@ui.page('/', response_timeout=10.0)  # default: 3.0 seconds
async def slow_page():
    # If this takes > 10s to complete, client gets a timeout error
    await asyncio.sleep(2)          # OK — under 10s
    ui.label('Loaded')
```

**Best practice**: Build a skeleton fast, then load data after `await client.connected()`:
```python
@ui.page('/')
async def index():
    # Fast initial render (under 3s)
    with ui.card().classes('w-full animate-pulse bg-grey-2 h-32'):
        pass  # skeleton placeholder
    content_area = ui.column()

    await ui.context.client.connected()  # respond to browser

    # Now load data without timeout pressure
    data = await fetch_data()
    content_area.clear()
    with content_area:
        render_content(data)
```

### Path Parameters
```python
@ui.page('/user/{user_id}')
def user_profile(user_id: int):
    ui.label(f'Profile for user {user_id}')

# Type annotations auto-convert: str, int, float, bool, complex
@ui.page('/product/{id}/{preview}')
def product(id: int, preview: bool):
    if preview:
        show_preview(id)
    else:
        show_full_product(id)
```

### Request & Query Parameters
```python
from fastapi import Request

@ui.page('/search')
def search(request: Request):
    query = request.query_params.get('q', '')
    ui.label(f'Searching for: {query}')
    # Access: /search?q=nicegui
```

---

## 4. Multicasting to Clients

### Push Update to ALL Clients on a Page
```python
from nicegui import app, ui

messages: list[str] = []

message_event = ui.refreshable  # or Event[T]

@ui.page('/')
def index():
    @ui.refreshable
    def message_list():
        for msg in messages:
            ui.label(msg)

    message_list()

    def post(e):
        messages.append(e.value)
        # Push to all connected clients on '/'
        for client in app.clients('/'):
            with client:
                message_list.refresh()

    ui.input('Message', on_change=post)
```

### Pattern: Background Task → All Clients
```python
import asyncio
from nicegui import app, ui

@app.on_startup
async def start_data_feed():
    async def feed():
        while True:
            data = await fetch_live_data()
            # Broadcast to all clients watching the dashboard
            for client in app.clients('/dashboard'):
                with client:
                    ui.notify(f'New data: {data}')
            await asyncio.sleep(5)

    asyncio.create_task(feed())
```

### Pattern: Event[T] (type-safe broadcast)
```python
from nicegui import ui
from nicegui.events import GenericEventArguments

# Preferred for multi-client updates — more efficient than app.clients() loop
from nicegui import background_tasks
from typing import Callable

# Define a typed event
class DataEvent:
    _handlers: list[Callable] = []

    @classmethod
    def subscribe(cls, handler: Callable):
        cls._handlers.append(handler)
        return handler

    @classmethod
    def emit(cls, data: dict):
        for handler in cls._handlers:
            handler(data)

# Better: use NiceGUI's built-in Event[T]
from nicegui.events import Event

data_updated: Event[dict] = Event()

@ui.page('/dashboard')
async def dashboard():
    status_label = ui.label('Waiting...')

    @data_updated.subscribe
    def on_update(data: dict):
        status_label.text = str(data['value'])

    await ui.context.client.connected()
    await ui.context.client.disconnected()
    data_updated.unsubscribe(on_update)  # cleanup

# Emit from anywhere (background task, API endpoint, etc.)
async def update_loop():
    while True:
        data = await fetch_data()
        data_updated.emit({'value': data})
        await asyncio.sleep(1)
```

---

## 5. Reconnect & Timeout Behavior

### Reconnect Timeout
When the browser loses connection (network hiccup, sleep), NiceGUI waits before giving up:

```python
ui.run(
    reconnect_timeout=3.0,   # seconds to wait for reconnect (default: 3.0)
)

# Per-page override
@ui.page('/', reconnect_timeout=10.0)
def index():
    ui.label('Reconnect-tolerant page')
```

### What Happens on Reconnect
- Client ID stays the same
- `app.storage.client` is **lost** (in-memory, tied to connection)
- `app.storage.tab` **survives** (keyed by tab token, not connection)
- `app.storage.user` **survives** (keyed by session cookie)
- UI elements are re-synced from server state

### Tab Token Persistence
NiceGUI assigns each browser tab a unique token stored in `sessionStorage`. This token:
- Persists across page reloads within the same tab
- Is lost when the tab closes
- Links `app.storage.tab` data to the tab across reconnects

---

## 6. Token & Session Identity

### How Identity Flows
```
Browser opens a new tab
       ↓
NiceGUI generates tab token → stored in sessionStorage
       ↓
Tab token → used as key for app.storage.tab
       ↓
Session cookie (if storage_secret set) → used as key for app.storage.user
       ↓
app.storage.browser['id'] = session cookie value
```

### Checking Browser Identity
```python
@ui.page('/')
def index():
    # Unique ID for this browser session (set by NiceGUI)
    browser_id = app.storage.browser['id']
    ui.label(f'Browser ID: {browser_id[:8]}...')

ui.run(storage_secret='your-secret')
```

### Cross-Tab State Without Redis
```python
# app.storage.user is automatically shared across all tabs for same browser
@ui.page('/tab-a')
def tab_a():
    def save():
        app.storage.user['shared_value'] = input_field.value

    input_field = ui.input(
        value=app.storage.user.get('shared_value', '')
    )
    ui.button('Save', on_click=save)

@ui.page('/tab-b')
def tab_b():
    # Reads the value saved from tab-a
    ui.label(f"From Tab A: {app.storage.user.get('shared_value', 'nothing yet')}")
```

### Production Storage with Redis
For apps with many users or requiring true persistence:
```python
# See integrations.md and redis_storage example
# Redis replaces the default file-based general storage backend
```

---

## 7. Background Tasks & App Lifecycle

### App Startup / Shutdown Hooks
```python
from nicegui import app, ui

@app.on_startup
async def startup():
    # Runs once when server starts
    await init_database()
    print('App started')

@app.on_shutdown
async def shutdown():
    # Runs when server stops (SIGTERM, Ctrl+C)
    await close_database()
    print('App stopped')

# Or inline:
app.on_startup(lambda: print('started'))
app.on_shutdown(lambda: print('stopped'))
```

### Running Background Tasks
```python
import asyncio
from nicegui import app, ui

@app.on_startup
async def start_background():
    async def loop():
        while True:
            # Do work
            data = await fetch_external_data()
            app.storage.general['last_data'] = data
            await asyncio.sleep(30)

    asyncio.create_task(loop())  # runs forever in background
```

### Accessing Storage Before App Starts
```python
# app.storage is available once nicegui is imported
# but ui.run() must be called for server to actually start
from nicegui import app, ui

# This runs at import time — storage not yet initialized
# app.storage.general['key'] = 'value'  # would fail

@app.on_startup
async def init():
    # Safe — runs after server is ready
    app.storage.general.setdefault('init_time', str(datetime.now()))
```

### Client Count & Active Connections
```python
from nicegui import app

# Count connected clients on a specific page
connected = len(list(app.clients('/')))
ui.label(f'{connected} users online')

# All connected clients across all pages
all_clients = list(app.clients())  # no path = all pages
```
