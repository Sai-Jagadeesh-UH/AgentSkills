# NiceGUI Internals — Event System

> Load when: adding custom events to elements, debugging event handlers, building Event[T] broadcasts, working with keyboard/mouse/scroll events, throttling events, using JS-side handlers.

## Table of Contents
1. [Two Event Systems](#1-two-event-systems)
2. [Element Event Listeners (browser → server)](#2-element-event-listeners-browser--server)
3. [event.on() — EventListener Configuration](#3-eventon--eventlistener-configuration)
4. [handle_event() — Dispatch Pipeline](#4-handle_event--dispatch-pipeline)
5. [Event[T] — Typed Server-Side Events](#5-eventt--typed-server-side-events)
6. [All Event Argument Types](#6-all-event-argument-types)
7. [JavaScript ↔ Python Bridge](#7-javascript--python-bridge)
8. [Background Tasks & Async Handlers](#8-background-tasks--async-handlers)
9. [Patterns & Recipes](#9-patterns--recipes)

---

## 1. Two Event Systems

| System | Direction | File | Use case |
|--------|-----------|------|----------|
| `EventListener` / `element.on()` | Browser → Server | `event_listener.py` | UI interactions (click, change, keydown) |
| `Event[T]` | Server → Server (or background) | `event.py` | Broadcast between Python components, multi-client push |

---

## 2. Element Event Listeners (browser → server)

Every `element.on('click', handler)` call creates an `EventListener` object:

```python
# event_listener.py
@dataclass
class EventListener:
    id: str              # uuid4 — used as listener_id in browser messages
    element_id: int      # which element this listener belongs to
    type: str            # camelCase event name (e.g. 'click', 'updateModelValue')
    args: Sequence       # which event args to send from browser ([None] = all)
    handler: Callable | None   # Python function to call
    js_handler: str | None     # JavaScript function to run on client
    throttle: float            # min seconds between events
    leading_events: bool       # fire on first occurrence
    trailing_events: bool      # fire on last occurrence after throttle
    request: Request | None    # HTTP request at subscription time (for storage.user access)
```

### Serialized to browser as:

```python
def to_dict(self):
    words = self.type.split('.')        # e.g. 'click.stop.prevent'
    type_ = words.pop(0)               # 'click'
    specials = [w for w in words if w in {'capture', 'once', 'passive'}]
    modifiers = [w for w in words if w in {'stop', 'prevent', 'self', 'ctrl', ...}]
    keys = [w for w in words if w not in specials + modifiers]
    return {
        'listener_id': self.id,
        'type': type_,
        'specials': specials,   # Vue event modifiers
        'modifiers': modifiers,
        'keys': keys,           # key filters for keyboard events
        'args': self.args,
        'throttle': self.throttle,
        'leading_events': self.leading_events,
        'trailing_events': self.trailing_events,
        'js_handler': self.js_handler,
    }
```

The browser sends:
```json
{
    "client_id": "...",
    "id": 42,
    "listener_id": "uuid-of-listener",
    "args": {"value": "new text"}
}
```

---

## 3. element.on() — EventListener Configuration

```python
element.on(
    type='click',              # event name (kebab or camel, converted to camelCase)
    handler=my_func,           # Python callback (optional)
    args=None,                 # which args to send: None=all, ['value']=subset
    throttle=0.0,              # minimum seconds between calls
    leading_events=True,       # call on first event
    trailing_events=True,      # call on last event (during throttle window)
    js_handler='...',          # client-side JS function (optional, replaces default)
)
```

### args filtering

By default (`args=None`) ALL event arguments are sent over WebSocket. Filter to reduce payload:

```python
# Send only 'value' field of the event (not the full event object)
input.on('update:model-value', handler, args=['value'])

# Multiple args
slider.on('change', handler, args=['value', 'oldValue'])

# Different args per nested event:
# args=[['x', 'y'], None]  — complex nested filtering
```

### Vue event modifier syntax

```python
# These work as dot-suffixed modifiers on the event type:
button.on('click.stop')           # stop propagation
button.on('click.prevent')        # preventDefault
button.on('click.once')           # fire only once
button.on('keydown.enter')        # only fires for Enter key
button.on('keydown.ctrl.shift.k') # Ctrl+Shift+K
```

### JavaScript handler (client-side only, no server call)

```python
# Pure JS: no network round-trip
element.on('click', js_handler='() => { console.log("clicked") }')

# JS pre-processes args then calls Python handler:
element.on('scroll',
    handler=my_python_fn,
    js_handler='(e) => emit(e.scrollTop)')  # emit() sends to Python
```

### Throttle

```python
# With throttle=1.0, leading_events=True, trailing_events=True (defaults):
# - First event fires immediately
# - Events during 1s window are suppressed
# - Last event fires after 1s window closes
slider.on('change', update_chart, throttle=1.0)
```

---

## 4. handle_event() — Dispatch Pipeline

When browser sends `event` message:

```python
# nicegui.py _on_event
def _on_event(_, msg):
    client = Client.instances.get(msg['client_id'])
    if not client or not client.has_socket_connection:
        return
    client.handle_event(msg)

# client.py handle_event
def handle_event(self, msg):
    with self:               # enter client context
        sender = self.elements.get(msg['id'])
        if sender is not None and not sender.is_ignoring_events:
            msg['args'] = [None if arg is None else json.loads(arg)
                          for arg in msg.get('args', [])]
            if len(msg['args']) == 1:
                msg['args'] = msg['args'][0]   # unwrap single arg
            sender._handle_event(msg)

# element.py _handle_event
def _handle_event(self, msg):
    listener = self._event_listeners[msg['listener_id']]
    storage.request_contextvar.set(listener.request)  # restore request context
    args = GenericEventArguments(sender=self, client=self.client, args=msg['args'])
    events.handle_event(listener.handler, args)
```

### events.handle_event() (the actual dispatcher)

```python
def handle_event(handler, arguments):
    if handler is None:
        return
    # Run handler in parent slot context (important for nested elements)
    parent_slot = arguments.sender.parent_slot or arguments.sender.client.layout.default_slot
    with parent_slot:
        if expects_arguments(handler):
            result = handler(arguments)   # passes EventArguments subclass
        else:
            result = handler()            # no-arg handler
    # If result is awaitable: schedule as background task
    if isinstance(result, Awaitable):
        background_tasks.create(wait_for_result(), name=str(handler))
```

**Key:** handler runs `with parent_slot:` — any UI elements created inside the handler are placed in the correct location in the tree.

---

## 5. Event[T] — Typed Server-Side Events

`Event[T]` (in `event.py`) is a server-side pub/sub channel for broadcasting between Python components:

```python
from nicegui import Event  # or from nicegui.event import Event

# Define (typically at module level)
data_ready: Event[dict] = Event()

# Subscribe (from UI context — auto-unsubscribes on client delete)
@ui.page('/')
def index():
    label = ui.label('waiting...')

    @data_ready.subscribe
    def on_data(payload: dict):
        label.text = str(payload['value'])

# Emit (from anywhere — background task, API endpoint, timer)
async def background_loop():
    while True:
        data = await fetch()
        data_ready.emit({'value': data})  # fire and forget
        # OR
        await data_ready.call({'value': data})  # wait for all handlers
        await asyncio.sleep(1)
```

### Auto-unsubscribe on client delete

When subscribed from within a `@ui.page` (where there's an active slot stack), the subscription is tied to the client:

```python
# event.py subscribe()
client: Client | None = None
if Slot.get_stack():
    callback_.slot = weakref.ref(context.slot)
    client = context.client
if client is not None and unsubscribe_on_delete is not False:
    client.on_delete(lambda: self.unsubscribe(callback))
```

**Result:** when the user navigates away and the client is deleted, the subscription is automatically removed. No manual cleanup needed.

### Waiting for next event (async)

```python
# event.py emitted()
async def emitted(self, timeout=None):
    future = asyncio.Future()
    def callback(*args):
        if not future.done():
            future.set_result(args[0] if len(args) == 1 else args or None)
    self.subscribe(callback)
    try:
        return await asyncio.wait_for(future, timeout)
    finally:
        self.unsubscribe(callback)

# Usage:
data = await data_ready.emitted(timeout=10.0)
# OR: event supports __await__
data = await data_ready  # waits for next emit, no timeout
```

### emit vs call

```python
event.emit(payload)          # fire and forget (async handlers run in background)
await event.call(payload)    # wait for ALL handlers to complete
```

---

## 6. All Event Argument Types

All are `@dataclass` with `KWONLY_SLOTS`. Inherit: `EventArguments → UiEventArguments → *`.

```python
# Base
UiEventArguments(sender: Element, client: Client)
GenericEventArguments(sender, client, args: Any)   # for element.on('custom-event')

# Input / Value
ValueChangeEventArguments(sender, client, value: Any, previous_value: Any)
# Used by: ui.input, ui.select, ui.slider, ui.checkbox, ui.date, ui.time, etc.

# Interactions
ClickEventArguments(sender, client)
KeyEventArguments(sender, client, action: KeyboardAction, key: KeyboardKey, modifiers: KeyboardModifiers)
MouseEventArguments(sender, client, type, image_x, image_y, button, buttons, alt, ctrl, meta, shift)
ScrollEventArguments(sender, client, vertical_position, vertical_percentage, ...)
JoystickEventArguments(sender, client, action, x, y)

# Selection
TableSelectionEventArguments(sender, client, selection: list[Any])
JsonEditorSelectEventArguments(sender, client, selection: dict)
JsonEditorChangeEventArguments(sender, client, content: dict, errors: dict)

# File
UploadEventArguments(sender, client, file: FileUpload)
MultiUploadEventArguments(sender, client, files: list[FileUpload])

# Chart
EChartPointClickEventArguments(sender, client, component_type, name, series_type, series_index, series_name, data_index, data, data_type, value)
EChartComponentClickEventArguments(sender, client, component_type, name)

# 3D scene
SceneClickEventArguments(sender, client, click_type, button, alt, ctrl, meta, shift, hits: list[SceneClickHit])
SceneDragEventArguments(sender, client, type, object_id, object_name, x, y, z)

# Color
ColorPickEventArguments(sender, client, color: str)

# xterm
XtermDataEventArguments(sender, client, data: str)
XtermBellEventArguments(sender, client)

# Mermaid
MermaidNodeClickEventArguments(sender, client, node_id: str)

# Slide list
SlideEventArguments(sender, client, side: SlideSide)

# Observable
ObservableChangeEventArguments(sender: ObservableCollection)
```

### KeyboardKey properties

```python
# events.py KeyboardKey
key.enter      # bool
key.escape
key.tab
key.backspace
key.space
key.arrow_left, arrow_right, arrow_up, arrow_down
key.page_up, page_down, home, end, insert, delete
key.f1 ... key.f12
key.is_cursorkey   # any arrow key
key.number         # int if Digit key, else None

# Compare by name or code:
if e.key == 'Enter':   # matches key.name or key.code
    ...
```

---

## 7. JavaScript ↔ Python Bridge

### Running JS from Python

```python
# client.py run_javascript
def run_javascript(self, code: str, timeout: float = 1.0) -> AwaitableResponse:
    request_id = str(uuid.uuid4())

    def send_and_forget():
        outbox.enqueue_message('run_javascript', {'code': code}, client_id)

    async def send_and_wait():
        outbox.enqueue_message('run_javascript', {'code': code, 'request_id': request_id}, client_id)
        await self.connected()
        return await JavaScriptRequest(request_id, timeout=timeout)

    return AwaitableResponse(send_and_forget, send_and_wait)

# Fire and forget (no await):
client.run_javascript('document.title = "Hello"')

# Get return value (must await):
title = await client.run_javascript('return document.title')
```

`AwaitableResponse` is lazy: `send_and_forget` runs if not awaited, `send_and_wait` runs if awaited.

### JS calling Python via emit()

In a `js_handler`, the special `emit()` function sends args to the Python handler:

```python
element.on('pointermove',
    handler=lambda e: print(e.args),
    js_handler='(e) => emit(e.clientX, e.clientY)',
    args=[['x', 'y']])  # ignored when js_handler sends its own args
```

### run_method — call Vue component method

```python
# element.py run_method
element.run_method('methodName', arg1, arg2)

# Internally:
client.run_javascript(f'return runMethod({element.id}, "methodName", [arg1, arg2])')
```

---

## 8. Background Tasks & Async Handlers

### Async event handlers are safe

```python
async def on_click():
    data = await fetch_data()   # fine — scheduled as background task
    label.text = data

button.on_click(on_click)
```

`handle_event()` detects awaitable results and wraps them in `background_tasks.create()`.

### background_tasks.create()

```python
# background_tasks.py
running_tasks: set[asyncio.Task] = set()  # prevents GC mid-execution

def create(coroutine, *, name='unnamed task', handle_exceptions=True) -> asyncio.Task:
    task = core.loop.create_task(coroutine, name=name)
    if handle_exceptions:
        task.add_done_callback(_handle_exceptions)   # forwards to app.handle_exception
    running_tasks.add(task)
    task.add_done_callback(running_tasks.discard)    # cleanup on done
    return task
```

### create_lazy — deduplicated tasks

```python
background_tasks.create_lazy(coroutine, name='my-task')
# If 'my-task' is already running: new coroutine queued
# If another 'my-task' is already queued: it's discarded (replaced)
# Use for: debounced search, chart refresh, anything where only the latest matters
```

### await_on_shutdown — graceful shutdown

```python
from nicegui.background_tasks import await_on_shutdown

@await_on_shutdown
async def save_data():
    await db.flush()

background_tasks.create(save_data())
# This task won't be cancelled during app shutdown
```

---

## 9. Patterns & Recipes

### Throttled real-time update

```python
# Throttle at browser: only 1 event per second, but always fire the last one
slider.on('input', update_chart, throttle=1.0, leading_events=True, trailing_events=True)
```

### Custom keyboard shortcut

```python
from nicegui.events import KeyEventArguments

def handle_keys(e: KeyEventArguments):
    if e.action.keydown:
        if e.modifiers.ctrl and e.key == 's':
            save()
        elif e.key.escape:
            close_dialog()

ui.keyboard(on_key=handle_keys)
```

### Event[T] for real-time dashboard

```python
# module level
new_reading: Event[dict] = Event()

@app.on_startup
async def data_stream():
    async def loop():
        async for reading in sensor.stream():
            new_reading.emit(reading)
    asyncio.create_task(loop())

@ui.page('/dashboard')
async def dashboard():
    chart = ui.echart({...})

    @new_reading.subscribe
    def on_reading(r: dict):
        chart.options['series'][0]['data'].append(r['value'])
        chart.update()

    await client.connected()
    await client.disconnected()
    # Auto-unsubscribed on client delete
```

### Prevent event if condition

```python
# Use js_handler to gate the Python call
button.on('click',
    handler=delete_item,
    js_handler='() => { if (confirm("Sure?")) emit() }')
# emit() with no args → handler called without args
```

### Detect specific click button (right-click)

```python
from nicegui.events import MouseEventArguments

def on_mouse(e: MouseEventArguments):
    if e.button == 2:    # right click
        show_context_menu(e.image_x, e.image_y)

image.on('mousedown', on_mouse, args=['button', 'image_x', 'image_y'])
```
