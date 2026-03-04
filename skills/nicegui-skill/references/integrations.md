# NiceGUI Integrations Reference

## Table of Contents
1. [FastAPI Integration](#1-fastapi-integration)
2. [HTTP Requests (httpx)](#2-http-requests-httpx)
3. [WebSockets](#3-websockets)
4. [SQLite with Tortoise ORM](#4-sqlite-with-tortoise-orm)
5. [Redis Storage](#5-redis-storage)
6. [ZeroMQ Messaging](#6-zeromq-messaging)
7. [Serial Port (PySerial)](#7-serial-port-pyserial)
8. [OpenCV Webcam](#8-opencv-webcam)
9. [PDF Generation](#9-pdf-generation)
10. [Stripe Payments](#10-stripe-payments)
11. [Third-party JS Libraries](#11-third-party-js-libraries)

---

## 1. FastAPI Integration

NiceGUI wraps FastAPI — use `app` directly:

```python
from nicegui import app, ui
from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse
import io

# REST API endpoint
@app.get('/api/users')
async def list_users(limit: int = 10):
    users = await db_fetch_users(limit=limit)
    return users

@app.post('/api/users')
async def create_user(user: UserModel):
    created = await db_create_user(user)
    return created

@app.get('/api/report')
async def download_report():
    data = generate_csv_data()
    return StreamingResponse(
        io.StringIO(data),
        media_type='text/csv',
        headers={'Content-Disposition': 'attachment; filename=report.csv'},
    )

# NiceGUI page
@ui.page('/')
def index():
    ui.label('Dashboard')

# Mount NiceGUI on an existing FastAPI app
from fastapi import FastAPI
fastapi_app = FastAPI()

@fastapi_app.get('/api/health')
async def health():
    return {'status': 'ok'}

ui.run_with(fastapi_app, mount_path='/ui', storage_secret='changeme')
# Now: /ui serves NiceGUI, /api serves FastAPI
```

### Custom middleware
```python
from starlette.middleware.base import BaseHTTPMiddleware

class RequestLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        print(f'{request.method} {request.url.path}')
        response = await call_next(request)
        print(f'  → {response.status_code}')
        return response

app.add_middleware(RequestLogMiddleware)
```

### Static files and uploads
```python
import uuid, shutil
from pathlib import Path

UPLOAD_DIR = Path('/tmp/uploads')
UPLOAD_DIR.mkdir(exist_ok=True)

app.add_static_files('/uploads', str(UPLOAD_DIR))
app.add_static_files('/assets', 'assets')  # local directory

async def handle_upload(e):
    filename = f'{uuid.uuid4()}{Path(e.name).suffix}'
    dest = UPLOAD_DIR / filename
    dest.write_bytes(await e.file.read())
    ui.image(f'/uploads/{filename}').classes('w-48 rounded')
    ui.notify('Uploaded!', type='positive')

ui.upload(on_upload=handle_upload, auto_upload=True).classes('w-full')
```

---

## 2. HTTP Requests (httpx)

Always use `httpx.AsyncClient` inside async page functions:

```python
import httpx

@ui.page('/')
async def index():
    # Fetch data on page load
    async with httpx.AsyncClient() as client:
        r = await client.get('https://api.github.com/repos/zauberzeug/nicegui')
    data = r.json()

    ui.label(f"NiceGUI: {data['stargazers_count']} ⭐").classes('text-xl')
```

### Search as you type with debounce
```python
import asyncio

running_query: asyncio.Task | None = None
results_container = ui.column()

async def search(e):
    global running_query
    if running_query:
        running_query.cancel()
    query = e.value.strip()
    if not query:
        results_container.clear()
        return

    running_query = asyncio.create_task(_fetch_results(query))
    try:
        results = await running_query
        results_container.clear()
        with results_container:
            for r in results:
                ui.label(r['name'])
    except asyncio.CancelledError:
        pass

async def _fetch_results(query: str):
    await asyncio.sleep(0.3)  # debounce
    async with httpx.AsyncClient() as client:
        r = await client.get(
            'https://api.example.com/search',
            params={'q': query},
            timeout=5.0,
        )
    return r.json()['items']

ui.input('Search', on_change=search).classes('w-full')
```

### Parallel requests
```python
async def load_dashboard():
    async with httpx.AsyncClient() as client:
        users_task = client.get('/api/users')
        orders_task = client.get('/api/orders')
        stats_task = client.get('/api/stats')
        users_r, orders_r, stats_r = await asyncio.gather(
            users_task, orders_task, stats_task
        )
    render_dashboard(users_r.json(), orders_r.json(), stats_r.json())
```

---

## 3. WebSockets

### NiceGUI as WebSocket client
```python
import asyncio
import websockets
from nicegui import background_tasks, ui
from nicegui.events import Event

message_received = Event[str]()

async def listen_to_ws(url: str):
    async for websocket in websockets.connect(url):
        try:
            async for message in websocket:
                message_received.emit(message)
        except websockets.ConnectionClosed:
            await asyncio.sleep(1)  # reconnect

@app.on_startup
async def startup():
    background_tasks.create(listen_to_ws('ws://localhost:8765'))

@ui.page('/')
def index():
    log = ui.log().classes('w-full h-64')

    @message_received.subscribe
    def on_message(msg: str):
        log.push(msg)
```

### NiceGUI as WebSocket server
```python
import websockets.server

connections: set = set()

async def handle_connection(websocket):
    connections.add(websocket)
    try:
        async for message in websocket:
            # Broadcast to all other clients
            for conn in connections - {websocket}:
                await conn.send(message)
    finally:
        connections.discard(websocket)

@app.on_startup
async def start_ws_server():
    server = await websockets.serve(handle_connection, 'localhost', 8765)
    background_tasks.create(server.serve_forever())
```

---

## 4. SQLite with Tortoise ORM

```python
# models.py
from tortoise import Model, fields

class User(Model):
    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=100)
    email = fields.CharField(max_length=200, unique=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = 'users'


class Task(Model):
    id = fields.IntField(pk=True)
    title = fields.CharField(max_length=200)
    done = fields.BooleanField(default=False)
    user = fields.ForeignKeyField('models.User', related_name='tasks')
```

```python
# main.py
from tortoise import Tortoise
from nicegui import app, ui
from models import User, Task

@app.on_startup
async def init_db():
    await Tortoise.init(
        db_url='sqlite://db.sqlite3',
        modules={'models': ['models']},
    )
    await Tortoise.generate_schemas()

@app.on_shutdown
async def close_db():
    await Tortoise.close_connections()


@ui.page('/users')
@ui.refreshable
async def users_page():
    users = await User.all().order_by('name')

    with ui.column().classes('w-full max-w-2xl gap-4'):
        ui.label('Users').classes('text-2xl font-bold')

        for user in users:
            with ui.card().classes('w-full p-4'):
                with ui.row().classes('w-full items-center justify-between'):
                    with ui.column():
                        ui.label(user.name).classes('font-medium')
                        ui.label(user.email).classes('text-sm text-grey-6')
                    with ui.row():
                        ui.button(icon='edit', on_click=lambda u=user: edit_user(u)).props('flat round')
                        ui.button(icon='delete', on_click=lambda u=user: delete_user(u)).props('flat round color=negative')

        # Add new user form
        with ui.card().classes('w-full p-4 border-dashed'):
            new_name = ui.input('Name').classes('w-full')
            new_email = ui.input('Email').classes('w-full')

            async def add_user():
                await User.create(name=new_name.value, email=new_email.value)
                users_page.refresh()

            ui.button('Add User', on_click=add_user).props('color=primary')


async def delete_user(user: User):
    await user.delete()
    users_page.refresh()
    ui.notify(f'Deleted {user.name}', type='positive')
```

---

## 5. Redis Storage

```python
import redis.asyncio as redis
import json

# Setup
redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)

@app.on_startup
async def check_redis():
    await redis_client.ping()
    print('Redis connected')

# Usage
async def set_value(key: str, value, ttl: int = 3600):
    await redis_client.set(key, json.dumps(value), ex=ttl)

async def get_value(key: str):
    raw = await redis_client.get(key)
    return json.loads(raw) if raw else None

# Session-like usage
async def get_user_session(session_id: str) -> dict:
    return await get_value(f'session:{session_id}') or {}

async def save_user_session(session_id: str, data: dict):
    await set_value(f'session:{session_id}', data, ttl=86400)  # 24h


# Pub/Sub for real-time updates
message_event = Event[str]()

async def redis_subscriber():
    pubsub = redis_client.pubsub()
    await pubsub.subscribe('app:notifications')
    async for message in pubsub.listen():
        if message['type'] == 'message':
            message_event.emit(message['data'])

@app.on_startup
async def start_redis_subscriber():
    background_tasks.create(redis_subscriber())
```

---

## 6. ZeroMQ Messaging

```python
import asyncio
import zmq
import zmq.asyncio

context = zmq.asyncio.Context()
data_event = Event[dict]()

async def zmq_receiver():
    socket = context.socket(zmq.SUB)
    socket.connect('tcp://localhost:5555')
    socket.setsockopt(zmq.SUBSCRIBE, b'')  # subscribe to all

    while True:
        try:
            msg = await socket.recv_json()
            data_event.emit(msg)
        except Exception as e:
            print(f'ZMQ error: {e}')
            await asyncio.sleep(1)

@app.on_startup
async def start_zmq():
    background_tasks.create(zmq_receiver())

@ui.page('/')
def dashboard():
    label = ui.label('Waiting for data...')

    @data_event.subscribe
    def on_data(data: dict):
        label.text = str(data)
```

---

## 7. Serial Port (PySerial)

```python
import serial
from nicegui import run, app, ui, background_tasks

# Configure serial port
PORT = '/dev/ttyUSB0'  # Linux: /dev/ttyUSB0, Mac: /dev/cu.*, Windows: COM3
BAUD = 115200

port: serial.Serial | None = None

@app.on_startup
async def connect_serial():
    global port
    try:
        port = serial.Serial(PORT, BAUD, timeout=0.1)
        background_tasks.create(read_loop())
        print(f'Serial connected: {PORT}')
    except serial.SerialException as e:
        print(f'Serial error: {e}')

serial_data = Event[str]()

async def read_loop():
    while not app.is_stopped:
        if port and port.in_waiting:
            line = await run.io_bound(port.readline)
            if line:
                serial_data.emit(line.decode('utf-8', errors='replace').strip())
        await asyncio.sleep(0.01)


@ui.page('/')
def terminal():
    log = ui.log(max_lines=200).classes('w-full h-64 font-mono text-sm')

    @serial_data.subscribe
    def on_data(line: str):
        log.push(f'← {line}')

    def send(text: str):
        if port and port.is_open:
            port.write(f'{text}\n'.encode())
            log.push(f'→ {text}')
        else:
            ui.notify('Serial not connected', type='negative')

    with ui.row().classes('w-full items-center'):
        inp = ui.input(placeholder='Send command...').classes('flex-1')
        inp.on('keydown.enter', lambda e: [send(e.sender.value), setattr(inp, 'value', '')])
        ui.button('Send', on_click=lambda: send(inp.value)).props('color=primary')
```

---

## 8. OpenCV Webcam

```python
import cv2
import base64
from nicegui import run, app, ui, background_tasks

jpeg_frame = Event[bytes]()

async def capture_loop():
    cap = cv2.VideoCapture(0)
    try:
        while not app.is_stopped:
            ret, frame = cap.read()
            if not ret:
                break
            # Convert to JPEG
            ok, buf = await run.cpu_bound(cv2.imencode, '.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            if ok:
                jpeg_frame.emit(bytes(buf))
            await asyncio.sleep(0.033)  # ~30fps
    finally:
        cap.release()


@app.on_startup
async def start_capture():
    background_tasks.create(capture_loop())


@ui.page('/camera')
async def camera():
    await ui.context.client.connected()

    # Display using interactive image (base64 src updates)
    img = ui.image().classes('w-full max-w-2xl rounded')

    @jpeg_frame.subscribe
    def on_frame(jpeg: bytes):
        b64 = base64.b64encode(jpeg).decode()
        img.source = f'data:image/jpeg;base64,{b64}'
```

---

## 9. PDF Generation

```python
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table
from reportlab.lib.styles import getSampleStyleSheet
import io, uuid
from fastapi.responses import StreamingResponse

def generate_pdf(title: str, data: list[dict]) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph(title, styles['Title']))
    story.append(Spacer(1, 20))

    # Table
    if data:
        headers = list(data[0].keys())
        table_data = [headers] + [[str(row[h]) for h in headers] for row in data]
        table = Table(table_data)
        story.append(table)

    doc.build(story)
    return buffer.getvalue()


@ui.page('/report')
async def report_page():
    async def download():
        pdf_bytes = await run.cpu_bound(
            generate_pdf, 'Monthly Report', fetch_data()
        )
        file_id = str(uuid.uuid4())
        path = f'/download/report-{file_id}.pdf'

        @app.get(path)
        def serve_pdf():
            return StreamingResponse(
                io.BytesIO(pdf_bytes),
                media_type='application/pdf',
                headers={'Content-Disposition': f'attachment; filename=report.pdf'},
            )

        ui.download(path)
        await ui.context.client.disconnected()
        app.routes = [r for r in app.routes if r.path != path]

    ui.button('Download PDF', icon='download', on_click=download).props('color=primary')
```

---

## 10. Stripe Payments

```python
import stripe
from fastapi.responses import RedirectResponse

stripe.api_key = 'sk_test_...'
PRICE_ID = 'price_...'

@app.get('/checkout')
async def checkout():
    session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        line_items=[{'price': PRICE_ID, 'quantity': 1}],
        mode='payment',
        success_url='http://localhost:8080/success?session_id={CHECKOUT_SESSION_ID}',
        cancel_url='http://localhost:8080/cancel',
    )
    return RedirectResponse(session.url, status_code=303)


@app.post('/webhook')
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig = request.headers.get('stripe-signature')
    try:
        event = stripe.Webhook.construct_event(payload, sig, 'whsec_...')
        if event['type'] == 'checkout.session.completed':
            session = event['data']['object']
            # Fulfill order
            print(f"Payment received: {session['id']}")
    except stripe.error.SignatureVerificationError:
        return JSONResponse({'error': 'Invalid signature'}, status_code=400)
    return {'status': 'ok'}


@ui.page('/')
def store():
    with ui.card().classes('w-96 p-6'):
        ui.label('Pro Plan').classes('text-xl font-bold')
        ui.label('$29/month').classes('text-3xl font-bold text-primary')
        ui.button('Subscribe', icon='payment', on_click=lambda: ui.navigate.to('/checkout')).props('color=primary').classes('w-full mt-4')


@ui.page('/success')
async def success(session_id: str = ''):
    ui.label('Payment successful! 🎉').classes('text-2xl font-bold text-green-600 absolute-center')
```

---

## 11. Third-party JS Libraries

### Adding a chart library (Chart.js)
```python
ui.add_head_html('<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>')

chart_html = '''
<canvas id="myChart" width="400" height="200"></canvas>
<script>
const ctx = document.getElementById('myChart');
new Chart(ctx, {
    type: 'bar',
    data: {
        labels: ['Jan', 'Feb', 'Mar', 'Apr'],
        datasets: [{ label: 'Sales', data: [12, 19, 3, 5], backgroundColor: 'rgba(99, 102, 241, 0.8)' }]
    }
});
</script>
'''
ui.html(chart_html, sanitize=False)
```

### Node module integration
```python
# package.json must exist with the dependency
# Then reference via app.add_static_files
app.add_static_files('/node_modules', 'node_modules')
ui.add_head_html('<script type="module" src="/node_modules/some-lib/dist/index.js"></script>')
```

### FullCalendar plugin (custom element)
```python
# From the fullcalendar example
from fullcalendar import FullCalendar

options = {
    'initialView': 'dayGridMonth',
    'headerToolbar': {'left': 'prev,next today', 'center': 'title', 'right': 'dayGridMonth,timeGridWeek'},
    'events': [
        {'title': 'Team Meeting', 'start': '2024-03-15T10:00:00', 'end': '2024-03-15T11:00:00'},
    ],
}

def on_click(e):
    ui.notify(f'Event clicked: {e.args}')

calendar = FullCalendar(options, on_click=on_click)
calendar.add_event('New Event', '2024-03-20 14:00', '2024-03-20 15:00')
calendar.remove_event('event-id')
```
