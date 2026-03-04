# NiceGUI Internals — Rendering Pipeline

> Load when: debugging why updates are slow/not arriving, understanding WebSocket messages, diagnosing reconnect issues, optimizing render throughput.

## Table of Contents
1. [Full Update Flow](#1-full-update-flow)
2. [Outbox — Batching Engine](#2-outbox--batching-engine)
3. [Client Structure & Layout Tree](#3-client-structure--layout-tree)
4. [Initial Page Build — build_response()](#4-initial-page-build--build_response)
5. [Socket.IO Message Types](#5-socketio-message-types)
6. [Reconnect & Message Rewind](#6-reconnect--message-rewind)
7. [Client Lifecycle — Handshake to Delete](#7-client-lifecycle--handshake-to-delete)
8. [JavaScript Component Loading](#8-javascript-component-loading)
9. [Performance Implications](#9-performance-implications)

---

## 1. Full Update Flow

```
Python mutates element (e.g. label.text = 'new')
  ↓
Element.update() → outbox.enqueue_update(element)
  ↓
outbox.updates[element.id] = element  (WeakValueDictionary)
outbox._enqueue_event.set()           (wakes the outbox coroutine)
  ↓
Outbox.loop() wakes on next event loop tick
  ↓
Checks: client.has_socket_connection?
  → No: sleeps 0.1s, retries (updates accumulate)
  → Yes: proceeds
  ↓
Collects: {element_id: element._to_dict() for all pending updates}
  ↓
If new JS components needed: emits 'load_js_components' first
  ↓
Emits: sio.emit('update', {element_id: dict, ...}, room=client_id)
  ↓
Browser Vue app receives update, patches virtual DOM
  ↓
DOM updated, user sees change
```

**All mutations within one event loop tick are batched into one `update` message.**

---

## 2. Outbox — Batching Engine

```python
class Outbox:
    updates: WeakValueDictionary[int, Element | Deleted]
    # WeakValueDictionary: if element is GC'd, auto-removed
    # Multiple enqueue_update() calls for same element → only latest _to_dict() sent

    messages: deque[Message]
    # (client_id, message_type, payload) — explicit messages like 'open', 'download'

    message_history: deque[HistoryEntry]
    # (message_id, timestamp, message) — kept for reconnect rewind
```

### Enqueue methods

```python
outbox.enqueue_update(element)          # schedules element._to_dict() to be sent
outbox.enqueue_delete(element)          # schedules element removal (sends None for that id)
outbox.enqueue_message(type, data, target_id)  # sends arbitrary message
```

### Loop behavior (source-accurate)

```python
async def loop(self):
    self._enqueue_event = asyncio.Event()
    self._enqueue_event.set()  # fire immediately on start

    while not self._should_stop:
        if not self._enqueue_event.is_set():
            await asyncio.wait_for(self._enqueue_event.wait(), timeout=1.0)

        if not client.has_socket_connection:
            await asyncio.sleep(0.1)  # wait for connection, don't lose updates
            continue

        self._enqueue_event.clear()

        # Collect all pending updates in one dict
        data = {id: None if deleted else element._to_dict()
                for id, element in self.updates.items()}
        self.updates.clear()

        # Check for new JS components to load
        # ... emit 'load_js_components' if needed ...

        await self._emit((client_id, 'update', data))

        # Send any explicit messages
        for message in self.messages:
            await self._emit(message)
        self.messages.clear()
```

### Deleted elements

```python
outbox.enqueue_delete(element)
# → outbox.updates[element.id] = deleted  (sentinel Deleted instance)
# → serialized as None in the update dict
# → browser removes the element from DOM
```

---

## 3. Client Structure & Layout Tree

Every `Client` gets this DOM tree created on initialization:

```
q-layout [view="hhh lpr fff"] .nicegui-layout     ← client.layout
  └── q-page-container                             ← client.page_container
        └── q-page
              └── div.nicegui-content              ← client.content
```

**`with client:`** → enters `client.content` (the nicegui-content div). All `@ui.page` functions build inside `client.content`.

**Top-level layout elements** (`ui.header`, `ui.left_drawer`, `ui.footer`) must be direct children of `client.content` — they're Quasar layout components that expect to live at the top level of `q-layout`.

```python
# In helpers.py
def require_top_level_layout(element):
    parent = context.slot.parent
    if parent != parent.client.content:
        raise RuntimeError(
            f'Top level layout element "{element.__class__.__name__}" '
            'cannot be nested inside another element.'
        )
```

### Client storage

```python
client.storage   # ObservableDict = app.storage.client
                 # in-memory, per connection, cleared on disconnect
```

---

## 4. Initial Page Build — build_response()

When a browser first requests a page, the server:

1. Calls the `@ui.page` function in a `with Client(page, request=request):` context
2. Python code runs synchronously, building the element tree in-memory
3. `client.build_response(request)` is called, which:
   - Serializes ALL elements: `{id: element._to_dict() for id, element in client.elements.items()}`
   - Calls `generate_resources()` to collect all Vue/JS dependencies
   - Renders `index.html` Jinja2 template with full state embedded as JSON
   - Returns HTTP response with `Cache-Control: no-store`

The initial HTML contains the **complete element tree as JSON** so the first paint shows the full UI without waiting for WebSocket.

```python
# client.py build_response() key context vars sent to template:
{
    'elements': json.dumps({id: el._to_dict() for id, el in self.elements.items()}),
    'imports': json.dumps(imports),        # importmap for ES modules
    'js_imports': '\n'.join(js_imports),   # component registration
    'vue_config': json.dumps(quasar_config),
    'socket_io_js_query_params': {         # connects WebSocket after page loads
        'client_id': self.id,
        'next_message_id': self.outbox.next_message_id,
        'implicit_handshake': not _is_prefetch(request),
    }
}
```

**Outbox is cleared** (`outbox.updates.clear()`) before building the response — elements already embedded in HTML don't need to be resent via WebSocket.

---

## 5. Socket.IO Message Types

### Server → Browser

| Message | When sent | Payload |
|---------|-----------|---------|
| `update` | Element mutation | `{element_id: dict_or_null, ...}` |
| `load_js_components` | New JS component first used | `{components: [{key, tag}, ...]}` |
| `run_javascript` | `client.run_javascript()` | `{code, request_id?}` |
| `open` | `ui.navigate.to()` | `{path, new_tab}` |
| `download` | `ui.download()` | `{src, filename, media_type}` |
| `notify` | `ui.notify()` | notification payload |

### Browser → Server

| Message | When sent | Handler |
|---------|-----------|---------|
| `handshake` | After WebSocket connects | `_on_handshake` |
| `event` | User interaction | `_on_event` → `client.handle_event(msg)` |
| `javascript_response` | Result of `run_javascript` | `_on_javascript_response` |
| `ack` | Browser acknowledges messages | `_on_ack` → `outbox.prune_history` |
| `log` | Browser logs forwarded | `_on_log` |

### Message structure

Every emitted message gets a `_id` field:
```python
data['_id'] = self.next_message_id
await sio.emit(message_type, data, room=client_id)
self.next_message_id += 1
```

The browser sends `ack` messages with `next_message_id` confirming received messages.

---

## 6. Reconnect & Message Rewind

When a browser reconnects (network hiccup, laptop sleep), it sends its last known `next_message_id` in the handshake. The server rewinds and replays missed messages:

```python
def try_rewind(self, target_message_id: int) -> None:
    if self.next_message_id == target_message_id:
        return  # nothing missed

    while self.message_history:
        self.next_message_id, _, message = self.message_history.pop()
        self.messages.appendleft(message)  # prepend to resend queue
        if self.next_message_id == target_message_id:
            self.message_history.clear()
            return

    # Target not in history → full page reload
    self.client.run_javascript('window.location.reload()')
```

### History retention window

```python
max_age = ping_interval + ping_timeout + reconnect_timeout
# e.g. with reconnect_timeout=3.0: ~3s * 0.8 + ~3s * 0.4 + 3.0 ≈ 6.6 seconds
# Also limited by: app.config.message_history_length (default: 1000)
```

### Ping interval tuning (from nicegui.py)

```python
sio.eio.ping_interval = max(reconnect_timeout * 0.8, 4)
sio.eio.ping_timeout = max(reconnect_timeout * 0.4, 2)
```

These are set relative to `reconnect_timeout` so the WebSocket keepalive matches the reconnect window.

---

## 7. Client Lifecycle — Handshake to Delete

### Handshake (browser → server)

```python
# nicegui.py _on_handshake
client.tab_id = data['tab_id']              # from sessionStorage in browser
sio.enter_room(sid, client.id)             # Socket.IO room = client.id
client.handle_handshake(sid, document_id, next_message_id)
await app.storage._create_tab_storage(client.tab_id)
```

`handle_handshake()` in client.py:
- Sets `_connected` event → `await client.connected()` returns
- Cancels any pending delete task (reconnect scenario)
- Calls `try_rewind(next_message_id)` if provided
- Invokes all `connect_handlers` and `app._connect_handlers`

### Disconnect

```python
# nicegui.py _on_disconnect
client.handle_disconnect(sid)
```

`handle_disconnect()` in client.py:
1. Sets `tab_id = None` → `has_socket_connection` becomes False
2. Invokes `disconnect_handlers` + `app._disconnect_handlers`
3. Starts a background task: `asyncio.sleep(reconnect_timeout)` then `client.delete()`

If browser reconnects before timeout → `handle_handshake()` cancels the delete task.

### Delete (permanent)

```python
client.delete()
# → delete_handlers called
# → _deleted_event.set() → await client.disconnected() returns
# → remove_all_elements() (binding cleanup for all elements)
# → outbox.stop()
# → del Client.instances[self.id]
```

### Pruning stale clients

```python
# Runs every 10 seconds (set in nicegui.py _startup)
Client.prune_instances(client_age_threshold=60.0)
# Removes clients that:
# - have no socket connection
# - have no pending delete task
# - were created > 60 seconds ago
```

---

## 8. JavaScript Component Loading

### Vue SFCs (.vue files)

Compiled at import time (not per-request) using `VBuild`:
```python
# dependencies.py register_vue_component
v = VBuild(path)
vue_components[key] = VueComponent(key, name, path, html=v.html, script=v.script, style=v.style)
```

Sent in initial HTML via `generate_resources()`:
- `vue_html`: component `<template>` tags
- `js_imports`: `import {default as MyWidget} from "url"; app.component("nicegui-mywidget", MyWidget);`

### JS Components (.js files)

Loaded lazily — only when first used by a connected client:
```python
# outbox.loop()
js_components = [
    component
    for element in self.updates.values()
    if isinstance(element.component, JsComponent)
    and component.name not in self._loaded_components
]
if js_components:
    await self._emit((client_id, 'load_js_components', {
        'components': [{'key': c.key, 'tag': c.tag} for c in js_components]
    }))
    self._loaded_components.update(c.name for c in js_components)
```

### Library importmap

All libraries registered via `register_library()` are added to the ES module importmap in the initial HTML:
```json
{
    "vue": "/_nicegui/3.8.0/static/vue.esm-browser.prod.js",
    "quasar": "/_nicegui/3.8.0/libraries/abc123",
    "mylib": "/_nicegui/3.8.0/libraries/def456"
}
```

---

## 9. Performance Implications

### One update per element per tick

Because `outbox.updates` is a `WeakValueDictionary` (keyed by element ID), calling `element.update()` 100 times in one sync block still only sends ONE `_to_dict()` snapshot — the final state.

```python
# This sends ONE update, not 100
for i in range(100):
    label.text = str(i)  # overwrites previous, only last value sent
# → sent: {label.id: {'tag': 'label', 'text': '99'}}
```

### Why large refreshables are expensive

`@ui.refreshable` calls `container.clear()` + rebuilds all children:
- `clear()` → `remove_elements(all descendants)` → N delete messages + binding cleanup
- Rebuild → N new element creates → N update messages

For 50-element refreshable: ~100 WebSocket messages. Prefer surgical updates.

### `update_method` for chart-like elements

Elements like `ui.echart` set `_update_method = 'update'` which tells the browser to call `component.update(newData)` instead of fully re-rendering. This is much faster for large datasets.

### Air mode (NiceGUI On Air)

When `on_air=True` in `ui.run()`, messages are also forwarded via `core.air.emit()` to a remote relay server, enabling external access. This doubles the emit cost per message.
