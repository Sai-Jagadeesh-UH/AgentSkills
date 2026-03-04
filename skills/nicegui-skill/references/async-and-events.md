# NiceGUI Async & Events Reference

## Table of Contents
1. [Async Page Lifecycle](#1-async-page-lifecycle)
2. [run.io_bound / run.cpu_bound](#2-runio_bound--runcpu_bound)
3. [Timer Patterns](#3-timer-patterns)
4. [Event System](#4-event-system)
5. [Multi-Client Events with Event[T]](#5-multi-client-events-with-eventt)
6. [Background Tasks](#6-background-tasks)
7. [Async Streaming (AI/SSE)](#7-async-streaming-aisse)
8. [Task Cancellation](#8-task-cancellation)
9. [JavaScript Interop](#9-javascript-interop)

---

## 1. Async Page Lifecycle

Every `@ui.page` function can be `async def`. This enables:
- Awaiting client connection before starting I/O
- Cleaning up resources when client disconnects
- Running async operations inline

```python
from nicegui import ui

@ui.page('/')
async def index():
    # 1. Build initial UI immediately
    status = ui.label('Connecting...')
    data_container = ui.column()

    # 2. Wait for WebSocket connection
    await ui.context.client.connected()
    status.text = 'Loading data...'

    # 3. Fetch data asynchronously
    import httpx
    async with httpx.AsyncClient() as client:
        r = await client.get('https://api.example.com/data')
    data = r.json()

    status.delete()
    with data_container:
        for item in data:
            ui.label(item['name'])

    # 4. Wait for client to disconnect (cleanup)
    await ui.context.client.disconnected()
    # cleanup code here (close DB connections, remove temp files, etc.)
```

**`connected()` vs `disconnected()`:**
- `await ui.context.client.connected()` — blocks until the browser WebSocket opens (typically < 100ms after page load)
- `await ui.context.client.disconnected()` — blocks until the browser closes (tab closed, navigation away)

**Common pattern — register cleanup routes:**
```python
@ui.page('/')
async def index():
    # Register a one-time download endpoint
    download_path = f'/download/{uuid.uuid4()}.csv'

    @app.get(download_path)
    def download():
        return StreamingResponse(generate_csv(), media_type='text/csv')

    ui.button('Download', on_click=lambda: ui.download(download_path))

    # Remove the route when client disconnects
    await ui.context.client.disconnected()
    app.routes = [r for r in app.routes if r.path != download_path]
```

---

## 2. run.io_bound / run.cpu_bound

NiceGUI runs on asyncio. Blocking calls freeze the event loop. Use `run` for blocking code:

```python
from nicegui import run

# I/O bound (file read, serial port, blocking network)
async def read_serial():
    line = await run.io_bound(port.readline)   # runs in thread pool
    log.push(line.decode())

# CPU bound (image processing, heavy math)
async def process_frame():
    result = await run.cpu_bound(cv2.imencode, '.jpg', frame)  # runs in process pool

# With arguments
async def load_file(path: str):
    content = await run.io_bound(Path(path).read_bytes)

# Lambda/closure
await run.io_bound(lambda: heavy_blocking_function(arg1, arg2))
```

**When to use which:**
| Operation | Use |
|-----------|-----|
| File I/O | `run.io_bound` |
| Database queries (sync ORM) | `run.io_bound` |
| Serial port | `run.io_bound` |
| Image/video processing | `run.cpu_bound` |
| Compression/encryption | `run.cpu_bound` |
| Pure async (httpx, aiofiles) | `await` directly |

---

## 3. Timer Patterns

### Basic repeating timer
```python
label = ui.label('0')
count = {'n': 0}

def tick():
    count['n'] += 1
    label.text = str(count['n'])

ui.timer(1.0, tick)  # every 1 second
```

### One-shot timer
```python
# Show a message then hide it after 3 seconds
msg = ui.label('Saved!').classes('text-green-600')
ui.timer(3.0, msg.delete, once=True)
```

### Controllable timer
```python
timer = ui.timer(0.5, update_chart, active=False)

ui.button('Start', on_click=timer.activate)
ui.button('Pause', on_click=timer.deactivate)
ui.button('Single tick', on_click=lambda: ui.timer(0, update_chart, once=True))
```

### Timer with async callback
```python
async def poll_api():
    async with httpx.AsyncClient() as c:
        r = await c.get('https://api.example.com/status')
    status_label.text = r.json()['status']

ui.timer(10.0, poll_api)  # async callbacks work fine
```

### Timeout-based desktop polling
```python
@ui.page('/')
async def index():
    await ui.context.client.connected()
    pending = ui.label('Pending...')

    async def check():
        try:
            result = await ui.run_javascript('return window.ready', timeout=2.0)
            if result:
                pending.delete()
                ui.label('Ready!').classes('text-green-600')
                timer.deactivate()
        except TimeoutError:
            pass  # client may have disconnected

    timer = ui.timer(0.5, check)
```

---

## 4. Event System

### Element events
```python
# Click
ui.button('Click me', on_click=handler)

# Input events
inp = ui.input()
inp.on('keydown.enter', send_message)
inp.on('keyup', update_search)
inp.on('blur', save_draft)
inp.on('focus', clear_error)

# Keyboard modifiers
inp.on('keydown.ctrl.s', save)
inp.on('keydown.shift.enter', newline)

# Mouse events on image
img = ui.interactive_image(url)
img.on('mousedown', lambda e: handle_click(e.args['button'], e.args['x'], e.args['y']))

# Drag and drop
element.on('dragstart', handle_dragstart)
element.on('dragover.prevent', highlight)
element.on('drop', handle_drop)
```

### Value change events
```python
select = ui.select(options, value='a')
select.on_value_change(lambda e: print(e.value))

checkbox = ui.checkbox()
checkbox.on('update:model-value', handle_change)

# Or use bind
select.bind_value(state, 'selected')  # two-way — no event needed
```

### Global events
```python
# Listen for custom JS events
ui.on('my_custom_event', handle_event)

# Emit from JavaScript
ui.run_javascript("emitEvent('my_custom_event', {data: 'hello'})")
```

### Keyboard handler (global)
```python
from nicegui import events

def handle_key(e: events.KeyEventArguments):
    if not e.action.keydown:
        return

    # Arrow keys
    if e.key.arrow_left:  move_left()
    if e.key.arrow_right: move_right()
    if e.key.arrow_up:    move_up()
    if e.key.arrow_down:  move_down()

    # Special keys
    if e.key.escape:      close_modal()
    if e.key.enter:       confirm()
    if e.key.space:       toggle_play()
    if e.key.delete:      delete_selected()

    # Modifiers
    if e.modifiers.ctrl and e.key.s:   save()
    if e.modifiers.ctrl and e.key.z:   undo()
    if e.modifiers.shift and e.key.f:  fullscreen()

keyboard = ui.keyboard(on_key=handle_key)
# Disable:
keyboard.active = False
```

---

## 5. Multi-Client Events with Event[T]

`Event[T]` broadcasts from any context to all connected clients' subscribed handlers.

```python
from nicegui.events import Event

# Define shared events
message_received = Event[str]()       # str payload
data_updated = Event[dict]()          # dict payload
notification = Event()                 # no payload

@ui.page('/')
async def index():
    msg_label = ui.label('Waiting...')

    # Subscribe this client's handler
    @message_received.subscribe
    def on_message(text: str):
        msg_label.text = text

    # Alternative with async handler
    @data_updated.subscribe
    async def on_data(data: dict):
        await refresh_chart(data)

# Emit from anywhere (another coroutine, timer, background task, etc.)
message_received.emit('Hello from server!')
data_updated.emit({'values': [1, 2, 3]})
notification.emit()
```

**Use case — real-time chat:**
```python
messages: list[dict] = []
new_message = Event[dict]()

@ui.page('/')
async def chat():
    own_id = str(uuid.uuid4())

    @ui.refreshable
    def message_list():
        for msg in messages:
            sent = msg['sender_id'] == own_id
            ui.chat_message(
                text=msg['text'],
                name=msg['sender'],
                sent=sent,
                stamp=msg['time'],
            )

    container = ui.column().classes('w-full flex-grow overflow-y-auto')
    with container:
        message_list()

    @new_message.subscribe
    def on_new_message(msg: dict):
        messages.append(msg)
        message_list.refresh()
        ui.run_javascript('window.scrollTo(0, document.body.scrollHeight)')

    async def send(text: str):
        msg = {
            'text': text,
            'sender': app.storage.user.get('username', 'Anonymous'),
            'sender_id': own_id,
            'time': datetime.now().strftime('%H:%M'),
        }
        new_message.emit(msg)
        inp.value = ''

    with ui.row().classes('w-full items-center'):
        inp = ui.input(placeholder='Message...').classes('flex-1').on('keydown.enter', lambda e: send(e.sender.value))
        ui.button(icon='send', on_click=lambda: send(inp.value)).props('flat round color=primary')
```

---

## 6. Background Tasks

### `background_tasks.create()`
Fire-and-forget async tasks that run independently of any page.

```python
from nicegui import background_tasks

async def process_upload(file_content: bytes, filename: str):
    result = await run.cpu_bound(analyze_file, file_content)
    # Notify all clients when done
    upload_complete.emit({'filename': filename, 'result': result})

async def handle_upload(e):
    content = await e.file.read()
    background_tasks.create(process_upload(content, e.name))
    ui.notify('Processing started in background')
```

### Worker pattern (queue + progress)
```python
import asyncio

class Worker:
    def __init__(self):
        self.progress: float = 0.0
        self.is_running: bool = False
        self._queue: asyncio.Queue = None

    async def run(self, generator_func):
        self._queue = asyncio.Queue()
        self.is_running = True
        self.progress = 0.0

        background_tasks.create(self._run_generator(generator_func))
        background_tasks.create(self._consume_queue())

    async def _run_generator(self, func):
        try:
            for progress in func():
                await self._queue.put(progress)
        finally:
            await self._queue.put(None)  # sentinel

    async def _consume_queue(self):
        while True:
            progress = await self._queue.get()
            if progress is None:
                self.is_running = False
                break
            self.progress = progress


# Usage
worker = Worker()

def heavy_task():
    for i in range(100):
        time.sleep(0.05)  # blocking work
        yield (i + 1) / 100  # progress 0.0 - 1.0

progress_bar = ui.linear_progress(value=0).classes('w-full')
progress_bar.bind_value_from(worker, 'progress')

ui.button('Start', on_click=lambda: background_tasks.create(worker.run(heavy_task)))
```

---

## 7. Async Streaming (AI/SSE)

### Streaming LLM responses
```python
from langchain_openai import ChatOpenAI

@ui.page('/')
def index():
    llm = ChatOpenAI(model_name='gpt-4o-mini', streaming=True)
    messages = ui.column().classes('w-full gap-2')

    async def send(question: str):
        inp.value = ''
        with messages:
            ui.chat_message(text=question, name='You', sent=True)
            response_msg = ui.chat_message(name='AI', sent=False)
            spinner = ui.spinner(type='dots')

        response_text = ''
        async for chunk in llm.astream(question):
            response_text += chunk.content
            response_msg.clear()
            with response_msg:
                ui.markdown(response_text)
            ui.run_javascript('window.scrollTo(0, document.body.scrollHeight)')

        messages.remove(spinner)

    inp = ui.input(placeholder='Ask something...').classes('w-full')
    inp.on('keydown.enter', lambda e: send(e.sender.value))
```

### Async subprocess streaming
```python
import asyncio
import shlex

async def run_command(command: str, output: ui.log):
    process = await asyncio.create_subprocess_exec(
        *shlex.split(command),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    async for line in process.stdout:
        output.push(line.decode().rstrip())
    await process.wait()
    output.push(f'\nExited with code {process.returncode}')

log = ui.log().classes('w-full h-64 font-mono text-sm')
cmd = ui.input('Command').classes('w-full')
ui.button('Run', on_click=lambda: background_tasks.create(run_command(cmd.value, log)))
```

### Async httpx streaming
```python
async def stream_download(url: str):
    progress = ui.linear_progress(value=0).classes('w-full')
    label = ui.label('Downloading...')

    async with httpx.AsyncClient() as client:
        async with client.stream('GET', url) as r:
            total = int(r.headers.get('content-length', 0))
            downloaded = 0
            chunks = []
            async for chunk in r.aiter_bytes(chunk_size=8192):
                chunks.append(chunk)
                downloaded += len(chunk)
                if total:
                    progress.value = downloaded / total

    label.text = f'Downloaded {downloaded} bytes'
    return b''.join(chunks)
```

---

## 8. Task Cancellation

### Cancelling in-flight queries
```python
import asyncio

running_query: asyncio.Task | None = None

async def search(e):
    global running_query

    # Cancel previous search
    if running_query:
        running_query.cancel()

    if not e.value.strip():
        results.clear()
        return

    running_query = asyncio.create_task(_do_search(e.value))
    try:
        data = await running_query
        _render_results(data)
    except asyncio.CancelledError:
        pass  # new search superseded this one


async def _do_search(query: str):
    async with httpx.AsyncClient() as client:
        r = await client.get(f'https://api.example.com/search?q={query}')
    return r.json()


results = ui.column().classes('w-full')
ui.input('Search', on_change=search).classes('w-full')
```

---

## 9. JavaScript Interop

### Call JS, get return value
```python
# Simple expressions
value = await ui.run_javascript('return window.innerWidth')
scroll_top = await ui.run_javascript('return document.documentElement.scrollTop')

# Complex expressions
result = await ui.run_javascript('''
    const items = document.querySelectorAll('.item');
    return Array.from(items).map(el => el.textContent);
''')

# With timeout
try:
    data = await ui.run_javascript('return window.externalData', timeout=5.0)
except TimeoutError:
    ui.notify('Timed out waiting for data')
```

### Fire-and-forget JS
```python
# Scroll to bottom
ui.run_javascript('window.scrollTo(0, document.body.scrollHeight)')

# Click a DOM element
ui.run_javascript('document.getElementById("my-btn").click()')

# Store in localStorage
ui.run_javascript(f'localStorage.setItem("theme", "{theme}")')

# Reload the page
ui.run_javascript('window.location.reload()')
```

### Custom JS events → Python handlers
```python
# Add JS that emits custom events
ui.add_body_html('''
<script>
    document.addEventListener('visibilitychange', function() {
        emitEvent('visibility_change', {hidden: document.hidden});
    });
</script>
''')

# Handle in Python
def on_visibility(e):
    if e.args.get('hidden'):
        print('Tab hidden')
    else:
        print('Tab visible')

ui.on('visibility_change', on_visibility)
```
