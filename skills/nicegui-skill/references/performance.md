# NiceGUI Performance & Optimization Reference

## Table of Contents
1. [How NiceGUI Renders — The Mental Model](#1-how-nicegui-renders--the-mental-model)
2. [Network Round-Trip Reduction](#2-network-round-trip-reduction)
3. [Render Efficiency](#3-render-efficiency)
4. [Data Loading Patterns](#4-data-loading-patterns)
5. [Timer & Polling Optimization](#5-timer--polling-optimization)
6. [Static Assets & Caching](#6-static-assets--caching)
7. [Memory & Connection Management](#7-memory--connection-management)
8. [Performance Anti-Patterns](#8-performance-anti-patterns)
9. [Profiling & Debugging Slowness](#9-profiling--debugging-slowness)

---

## 1. How NiceGUI Renders — The Mental Model

**Every element property change → WebSocket message → browser DOM patch**

```
Python:  label.text = 'new value'
           ↓
         Serializes diff to JSON
           ↓ (WebSocket frame)
Browser: Vue patches the virtual DOM
           ↓
         User sees update
```

**Implications:**
- Updating 100 labels in a loop = 100 WebSocket frames = noticeable lag
- `@ui.refreshable` tears down and rebuilds its subtree (many frames)
- Surgical updates (`element.text = x`) send one frame — much cheaper
- `element.visible = False` then rebuild → only final state is sent (NiceGUI batches within a sync block)

**The event loop rule:** NiceGUI runs on asyncio. Any blocking call (DB query, file read, HTTP request without `await`) freezes ALL client updates until it returns. Always use async or offload.

---

## 2. Network Round-Trip Reduction

### Batch data fetches — one call per page load
```python
# ❌ BAD — N separate async calls, N round-trips to DB
@ui.page('/')
async def index():
    users = await get_users()         # round-trip 1
    orders = await get_orders()       # round-trip 2
    stats = await get_stats()         # round-trip 3

# ✅ GOOD — parallel fetches, one conceptual load
@ui.page('/')
async def index():
    import asyncio
    users, orders, stats = await asyncio.gather(
        get_users(),
        get_orders(),
        get_stats(),
    )
    render_page(users, orders, stats)
```

### Avoid per-element async fetches
```python
# ❌ BAD — each card fetches its own data
@ui.refreshable
def card_list(ids: list[str]):
    for item_id in ids:
        data = asyncio.run(fetch_item(item_id))  # BLOCKS event loop
        item_card(data)

# ✅ GOOD — one batch fetch, pass to renderer
@ui.refreshable
def card_list(items: list[dict]):
    for item in items:
        item_card(item)

# Caller fetches all at once
items = await fetch_all_items(ids)
card_list(items)
```

### Cache expensive reads with TTL
```python
import time
from functools import lru_cache

_cache: dict = {}

async def get_stats(ttl_seconds: int = 60) -> dict:
    key = 'stats'
    cached = _cache.get(key)
    if cached and time.time() - cached['ts'] < ttl_seconds:
        return cached['data']
    data = await db_fetch_stats()
    _cache[key] = {'data': data, 'ts': time.time()}
    return data
```

### Client-side filtering — send once, filter in browser
```python
# ❌ BAD — server refetch on every filter change
def update_filter(e):
    results = db.query(filter=e.value)  # new round-trip
    table.rows = results

# ✅ GOOD — load all data once, use table's built-in filter
all_data = await db.fetch_all()
table = ui.table(columns=cols, rows=all_data, row_key='id')
ui.input(placeholder='Filter...').bind_value(table, 'filter')
# Table filters client-side — no server call
```

---

## 3. Render Efficiency

### Surgical updates vs. full rebuild

```python
# ❌ BAD — rebuilds entire refreshable (many WebSocket frames)
status = {'value': 'ok'}

@ui.refreshable
def status_bar():
    ui.label(status['value']).classes('text-lg')
    # ... 20 other elements

def update_status(new: str):
    status['value'] = new
    status_bar.refresh()  # rebuilds all 20 elements

# ✅ GOOD — one element update (one WebSocket frame)
status_label = ui.label('ok').classes('text-lg')

def update_status(new: str):
    status_label.text = new
```

### Use `@ui.refreshable` correctly
Use it when the **structure** of the UI changes (different number of items, different types), not just values:

```python
# Good use — list length changes
todos: list[str] = []

@ui.refreshable
def todo_list():
    for todo in todos:
        with ui.row():
            ui.checkbox()
            ui.label(todo)

# Good use — conditional rendering based on data
@ui.refreshable
def content_area(mode: str):
    if mode == 'table':
        table_view()
    elif mode == 'card':
        card_view()
    else:
        empty_state()
```

### Batch UI construction — build before inserting
NiceGUI sends updates at the end of each event handler, not mid-execution. Build the full structure in one handler:

```python
# ✅ This sends all DOM changes in one batch after the function returns
def load_items(items: list):
    container.clear()
    with container:
        for item in items:
            item_card(item)
# All frames sent at once after the function completes
```

### Avoid re-renders during streaming
When streaming (AI output, log tailing, live data), update a single element's content rather than creating new elements:

```python
# ❌ BAD — creates new elements on each chunk
async def stream():
    async for chunk in llm.astream(prompt):
        ui.label(chunk)  # new element each time

# ✅ GOOD — update one element's content
response_md = ui.markdown('')
text = ''
async def stream():
    global text
    async for chunk in llm.astream(prompt):
        text += chunk.content
        response_md.content = text  # one element updated
```

---

## 4. Data Loading Patterns

### Pattern 1: Load on page entry (most common)
```python
@ui.page('/')
async def index():
    # Show skeleton while loading
    with ui.card().classes('w-full h-48 animate-pulse bg-grey-2'):
        pass
    loading_placeholder = ui.column()

    await ui.context.client.connected()

    # Load all data in parallel
    users, metrics = await asyncio.gather(fetch_users(), fetch_metrics())

    loading_placeholder.delete()
    render_dashboard(users, metrics)
```

### Pattern 2: Load on demand (tabs, lazy panels)
```python
loaded_tabs: set[str] = set()

async def on_tab_change(e):
    tab_name = e.value
    if tab_name in loaded_tabs:
        return  # already loaded — don't refetch
    loaded_tabs.add(tab_name)

    with ui.spinner():
        data = await fetch_tab_data(tab_name)
    tab_containers[tab_name].clear()
    with tab_containers[tab_name]:
        render_tab(data)

tabs.on_value_change(on_tab_change)
```

### Pattern 3: Pagination (avoid loading all rows)
```python
PAGE_SIZE = 25
current_page = {'n': 1}

@ui.refreshable
async def paged_table():
    offset = (current_page['n'] - 1) * PAGE_SIZE
    rows, total = await db.fetch_page(offset=offset, limit=PAGE_SIZE)
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE

    ui.table(columns=cols, rows=rows, row_key='id').classes('w-full')
    ui.pagination(
        value=current_page['n'],
        max=total_pages,
        direction_links=True,
        on_update_model_value=lambda e: [current_page.update(n=e), paged_table.refresh()]
    )

paged_table()
```

### Pattern 4: Infinite scroll
```python
all_items: list[dict] = []
loaded_count = {'n': 20}

@ui.refreshable
def item_list():
    for item in all_items[:loaded_count['n']]:
        item_row(item)

    if loaded_count['n'] < len(all_items):
        ui.button(
            f'Load more ({len(all_items) - loaded_count["n"]} remaining)',
            on_click=load_more,
        ).props('flat no-caps').classes('w-full mt-2')

def load_more():
    loaded_count['n'] = min(loaded_count['n'] + 20, len(all_items))
    item_list.refresh()
```

---

## 5. Timer & Polling Optimization

### Use push (Event[T]) over pull (timer) when possible
```python
# ❌ BAD — polling every second for something that rarely changes
ui.timer(1.0, lambda: update_all_displays())

# ✅ GOOD — push update only when data actually changes
data_changed = Event[dict]()

# Emit only when the data source changes
async def data_source_loop():
    last = None
    while True:
        current = await fetch_current_state()
        if current != last:
            data_changed.emit(current)
            last = current
        await asyncio.sleep(5)  # check every 5s, emit only on change
```

### Timer interval guidelines
| Update frequency | Interval | Use case |
|-----------------|----------|----------|
| Real-time stream | Event[T] | Chat, live logs, sensor data |
| Near-realtime | 0.5–1.0s | Live dashboards, stock prices |
| Regular refresh | 5–30s | Status checks, metrics |
| Slow polling | 60s+ | System health, slow APIs |
| One-shot | `once=True` | Post-load initialization |

### Stop timers when client disconnects
```python
@ui.page('/')
async def index():
    label = ui.label('...')
    timer = ui.timer(2.0, lambda: update(label))

    await ui.context.client.connected()
    await ui.context.client.disconnected()
    timer.deactivate()  # stop the timer — client is gone
```

### Debounce rapid events (search-as-you-type)
```python
import asyncio

_search_task: asyncio.Task | None = None

async def on_search_change(e):
    global _search_task
    if _search_task:
        _search_task.cancel()

    async def delayed_search():
        await asyncio.sleep(0.3)        # debounce: 300ms
        results = await search(e.value)
        render_results(results)

    _search_task = asyncio.create_task(delayed_search())

ui.input('Search', on_change=on_search_change)
```

---

## 6. Static Assets & Caching

### Serve static files — don't embed as base64
```python
# ❌ BAD — sends image bytes over WebSocket on every update
with open('logo.png', 'rb') as f:
    b64 = base64.b64encode(f.read()).decode()
ui.image(f'data:image/png;base64,{b64}')

# ✅ GOOD — browser caches the file, served over HTTP
app.add_static_files('/static', 'static')
ui.image('/static/logo.png')  # cached by browser
```

### Cache-control headers for static files
```python
from fastapi import Response

@app.get('/static/{filename}')
async def static_file(filename: str, response: Response):
    response.headers['Cache-Control'] = 'public, max-age=86400'  # 1 day
    return FileResponse(f'static/{filename}')
```

### Preload heavy resources (3D models, large images)
```python
ui.add_head_html('''
<link rel="preload" href="/static/model.stl" as="fetch" crossorigin>
<link rel="preload" href="/static/hero.jpg" as="image">
''')
```

### Optimize images before serving
- Resize to actual display size (don't serve 4K for a 200px thumbnail)
- Use WebP format (better compression than JPEG/PNG)
- Use `ui.image().props('loading=lazy')` for below-fold images

---

## 7. Memory & Connection Management

### Clean up per-client state on disconnect
```python
# Track per-client subscriptions
client_subscriptions: dict[str, list] = {}

@ui.page('/')
async def index():
    client_id = str(uuid.uuid4())
    client_subscriptions[client_id] = []

    def add_sub(handler):
        client_subscriptions[client_id].append(handler)
        return handler

    # Use subscriptions normally
    @add_sub
    @data_event.subscribe
    def on_data(d: dict):
        update_display(d)

    await ui.context.client.connected()
    await ui.context.client.disconnected()

    # Cleanup
    for handler in client_subscriptions.pop(client_id, []):
        data_event.unsubscribe(handler)
```

### Limit message history / log buffer size
```python
MAX_MESSAGES = 500

def append_message(msg: dict):
    messages.append(msg)
    if len(messages) > MAX_MESSAGES:
        messages.pop(0)  # trim oldest
```

### Close DB connections / file handles properly
```python
@app.on_shutdown
async def shutdown():
    await Tortoise.close_connections()
    redis_client.close()
    if serial_port:
        serial_port.close()
```

---

## 8. Performance Anti-Patterns

### ❌ Blocking the event loop
```python
# Any of these freeze all client updates
import time; time.sleep(5)
requests.get(url)  # sync HTTP
with open('huge.csv') as f: data = f.read()

# Fix: use async equivalents
await asyncio.sleep(5)
async with httpx.AsyncClient() as c: await c.get(url)
content = await run.io_bound(Path('huge.csv').read_text)
```

### ❌ Rebuilding entire page on small changes
```python
# Full page rebuild for one label change — DON'T
ui.navigate.to('/')  # forces full page reload

# Rebuild a huge refreshable — DON'T
@ui.refreshable
def entire_dashboard():
    kpi_section()
    chart_section()
    table_section()  # 500 rows

entire_dashboard.refresh()  # rebuilds everything for a counter change

# Fix: make refreshables small and targeted
@ui.refreshable
def kpi_section():
    ...  # only rebuild this
```

### ❌ Too many timers at short intervals
```python
# 10 components each with a 100ms timer = 100 WebSocket frames/sec
for metric in metrics:
    ui.timer(0.1, lambda m=metric: update_metric(m))

# Fix: one timer, update all at once
def update_all():
    for metric, label in zip(metrics, metric_labels):
        label.text = str(metric())
ui.timer(1.0, update_all)
```

### ❌ Sending large objects over WebSocket
```python
# Sending a full 10MB dataset through label.text
label.text = str(huge_dataframe.to_dict())

# Fix: paginate, summarize, or serve via HTTP endpoint
@app.get('/api/data')
async def get_data():
    return huge_dataframe.to_dict(orient='records')  # served over HTTP, cacheable
```

### ❌ Creating DOM elements in a loop without container
```python
# Creates DOM elements directly in root — hard to manage
for i in range(1000):
    ui.label(str(i))

# Fix: use scroll_area + pagination
with ui.scroll_area().classes('h-96'):
    for i in range(1000):
        ui.label(str(i))
# Or just paginate:
page_items = all_items[offset:offset+PAGE_SIZE]
```

---

## 9. Profiling & Debugging Slowness

### Measure async timing
```python
import time

async def timed(coro, label: str):
    start = time.monotonic()
    result = await coro
    elapsed = time.monotonic() - start
    print(f'[PERF] {label}: {elapsed*1000:.1f}ms')
    return result

users = await timed(fetch_users(), 'fetch_users')
```

### Identify WebSocket frame count
```python
# Add to SKILL.md context: NiceGUI sends a WebSocket frame per property change
# To count: open browser DevTools → Network → WS → count frames during an action
```

### Find blocking calls
```python
# Enable asyncio debug mode
import asyncio
asyncio.get_event_loop().set_debug(True)
# Logs warnings for coroutines that take > 100ms
```

### NiceGUI dev mode
```python
ui.run(
    reload=True,    # hot reload — shows Python errors inline
    # Check browser console for WebSocket errors
    # Check terminal for Python tracebacks
)
```
