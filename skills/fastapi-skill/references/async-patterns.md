# Async Patterns & Background Task Optimization

## Table of Contents
1. [Async First Principles](#async-first-principles)
2. [Async Database Patterns](#async-database)
3. [Async HTTP Client Patterns](#async-http-client)
4. [Background Tasks — FastAPI Native](#background-tasks-native)
5. [Task Queues — ARQ (Redis-based)](#arq-task-queue)
6. [Task Queues — Celery](#celery)
7. [Streaming Responses](#streaming)
8. [WebSockets & SSE](#websockets-sse)
9. [Concurrency Patterns](#concurrency-patterns)
10. [Profiling & Debugging Async](#profiling-async)

---

## Async First Principles {#async-first-principles}

### The Golden Rule

**Never block the event loop.** One blocking call in `async def` blocks ALL concurrent requests.

```python
# BAD — blocks event loop for all users during this call
@app.get("/bad")
async def bad_endpoint():
    time.sleep(2)              # BLOCKS all requests
    data = requests.get(url)   # BLOCKS all requests
    df = pd.read_csv("big.csv") # BLOCKS all requests

# GOOD — non-blocking
@app.get("/good")
async def good_endpoint():
    await asyncio.sleep(2)                           # yields control
    async with httpx.AsyncClient() as c:
        data = await c.get(url)                      # yields control
    df = await asyncio.to_thread(pd.read_csv, "big.csv")  # runs in thread pool
```

### When to Use `async def` vs `def`

| Scenario | Use | Reason |
|---|---|---|
| DB queries (asyncpg, motor) | `async def` | Awaitable I/O |
| External HTTP (httpx) | `async def` | Awaitable I/O |
| File I/O (aiofiles) | `async def` | Awaitable I/O |
| CPU-bound (pandas, numpy, ML) | `def` | Thread pool isolation |
| Subprocess calls | `def` or `asyncio.create_subprocess_exec` | Blocking unless async |
| Redis (redis.asyncio) | `async def` | Awaitable I/O |

### Running Blocking Code Safely

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor

# Thread pool for I/O-bound blocking code
@app.post("/process-csv")
async def process_csv(file: UploadFile):
    content = await file.read()
    # Run blocking pandas code in thread pool
    result = await asyncio.to_thread(analyze_with_pandas, content)
    return result

def analyze_with_pandas(content: bytes) -> dict:
    import pandas as pd
    df = pd.read_csv(io.BytesIO(content))
    return {"rows": len(df), "columns": list(df.columns)}

# Process pool for CPU-bound work (bypasses GIL)
executor = ProcessPoolExecutor(max_workers=4)

@app.post("/ml-inference")
async def ml_inference(data: InputData):
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(executor, run_model, data.features)
    return {"prediction": result}
```

---

## Async Database Patterns {#async-database}

### SQLAlchemy Async Setup

```python
# core/database.py
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)
from sqlalchemy.orm import DeclarativeBase

engine = create_async_engine(
    settings.database_url,
    pool_size=settings.db_pool_size,      # base connection count
    max_overflow=settings.db_max_overflow, # burst capacity
    pool_pre_ping=True,                   # verify connections before use
    pool_recycle=3600,                    # recycle every hour
    echo=settings.debug,                  # log SQL in debug mode
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # important: don't expire after commit
    autocommit=False,
    autoflush=False,
)

class Base(DeclarativeBase):
    pass

# Dependency
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

### Repository Pattern with Async

```python
# repositories/user.py
from sqlalchemy import select, func, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

class UserRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, user_id: UUID) -> User | None:
        return await self.db.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        result = await self.db.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()

    async def list_paginated(
        self, page: int = 1, size: int = 20, **filters
    ) -> tuple[list[User], int]:
        offset = (page - 1) * size

        # Run count and data queries concurrently
        count_query = select(func.count()).select_from(User)
        data_query = select(User).offset(offset).limit(size)

        # Apply filters
        for field, value in filters.items():
            if value is not None:
                count_query = count_query.where(getattr(User, field) == value)
                data_query = data_query.where(getattr(User, field) == value)

        # Execute both queries concurrently
        count_result, data_result = await asyncio.gather(
            self.db.execute(count_query),
            self.db.execute(data_query),
        )

        total = count_result.scalar()
        users = data_result.scalars().all()
        return users, total

    async def create(self, data: UserCreate, hashed_password: str) -> User:
        user = User(
            email=data.email,
            full_name=data.full_name,
            hashed_password=hashed_password,
        )
        self.db.add(user)
        await self.db.flush()  # get ID without committing
        await self.db.refresh(user)
        return user

    async def bulk_create(self, users: list[dict]) -> list[User]:
        # Efficient bulk insert
        instances = [User(**u) for u in users]
        self.db.add_all(instances)
        await self.db.flush()
        return instances
```

### Concurrent DB Queries

```python
# Execute multiple independent queries concurrently
@app.get("/dashboard")
async def dashboard(
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    # These 3 queries run CONCURRENTLY, not sequentially
    orders_task = db.execute(select(Order).where(Order.user_id == user.id))
    items_task = db.execute(select(Item).limit(10))
    stats_task = db.execute(select(func.count(Order.id)))

    orders_result, items_result, stats_result = await asyncio.gather(
        orders_task, items_task, stats_task
    )

    return {
        "orders": orders_result.scalars().all(),
        "featured_items": items_result.scalars().all(),
        "total_orders": stats_result.scalar(),
    }
```

---

## Async HTTP Client Patterns {#async-http-client}

### httpx Async Client — Best Practices

```python
# Reuse client across requests (connection pooling)
# Set up in lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(10.0, connect=5.0),
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        follow_redirects=True,
    ) as client:
        app.state.http_client = client
        yield

# Dependency to access shared client
def get_http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http_client

# Usage in service
async def fetch_external_data(
    url: str,
    client: httpx.AsyncClient = Depends(get_http_client),
) -> dict:
    response = await client.get(url)
    response.raise_for_status()
    return response.json()
```

### Parallel External API Calls

```python
@app.get("/aggregated")
async def aggregated_data(client: httpx.AsyncClient = Depends(get_http_client)):
    # Fire all requests concurrently
    results = await asyncio.gather(
        client.get("https://api1.example.com/data"),
        client.get("https://api2.example.com/data"),
        client.get("https://api3.example.com/data"),
        return_exceptions=True,  # don't fail all if one fails
    )

    output = {}
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            output[f"source_{i}"] = {"error": str(result)}
        else:
            output[f"source_{i}"] = result.json()

    return output
```

### Retry with Tenacity

```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(httpx.TransportError),
    reraise=True,
)
async def resilient_fetch(client: httpx.AsyncClient, url: str) -> dict:
    response = await client.get(url)
    response.raise_for_status()
    return response.json()
```

---

## Background Tasks — FastAPI Native {#background-tasks-native}

FastAPI's `BackgroundTasks` runs after the response is sent. Best for lightweight, fast tasks.

### Pattern 1 — In Endpoint

```python
from fastapi import BackgroundTasks

async def send_welcome_email(email: str, name: str):
    """Runs AFTER response is sent to client"""
    await email_service.send(
        to=email,
        subject=f"Welcome, {name}!",
        template="welcome",
    )

async def log_signup(user_id: UUID, ip: str):
    await audit_log.write(event="signup", user_id=user_id, ip=ip)

@app.post("/users/", response_model=UserRead, status_code=201)
async def create_user(
    user_data: UserCreate,
    background_tasks: BackgroundTasks,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    user = await user_service.create(db, user_data)

    # Schedule tasks — they run after this endpoint returns
    background_tasks.add_task(send_welcome_email, user.email, user.full_name)
    background_tasks.add_task(log_signup, user.id, request.client.host)

    return user  # returned immediately, tasks run after
```

### Pattern 2 — In Dependency (tasks accumulate)

```python
from fastapi import BackgroundTasks, Depends

async def get_db_with_audit(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    request: Request = None,
):
    """Dependency that automatically logs all mutations"""
    yield db
    # Schedule audit log after endpoint completes
    background_tasks.add_task(
        audit_service.log_request,
        method=request.method,
        path=request.url.path,
    )
```

### When NOT to use BackgroundTasks

Don't use for:
- Tasks that take > 30 seconds
- Tasks that need retry logic
- Tasks that must survive server crashes
- Distributed/multi-process tasks

Use ARQ or Celery instead.

---

## Task Queues — ARQ (Redis-based) {#arq-task-queue}

ARQ is async-native, lightweight, Redis-backed. Ideal for FastAPI.

```bash
pip install arq
```

### Worker Definition

```python
# workers/tasks.py
from arq import create_pool
from arq.connections import RedisSettings

# Define tasks as async functions
async def send_email(ctx: dict, to: str, subject: str, body: str):
    """ctx contains the worker context (DB pool, HTTP client, etc.)"""
    email_client = ctx["email_client"]
    await email_client.send(to=to, subject=subject, body=body)
    return {"sent_to": to}

async def process_upload(ctx: dict, file_id: UUID, user_id: UUID):
    db = ctx["db_pool"]
    async with db() as session:
        file = await session.get(UploadedFile, file_id)
        # Process file...
        file.status = "processed"
        await session.commit()

# Worker class
class WorkerSettings:
    functions = [send_email, process_upload]
    redis_settings = RedisSettings(host="localhost", port=6379)
    max_jobs = 10           # concurrent jobs per worker
    job_timeout = 300       # max seconds per job
    keep_result = 3600      # keep results for 1 hour
    retry_jobs = True
    max_tries = 3

    async def on_startup(ctx):
        ctx["db_pool"] = AsyncSessionLocal
        ctx["email_client"] = EmailClient(settings.smtp_host)

    async def on_shutdown(ctx):
        await ctx["email_client"].close()
```

### Enqueueing from FastAPI

```python
# In lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.arq_pool = await create_pool(RedisSettings())
    yield
    await app.state.arq_pool.close()

# Dependency
def get_task_queue(request: Request):
    return request.app.state.arq_pool

# In endpoint
@app.post("/users/")
async def create_user(
    data: UserCreate,
    queue = Depends(get_task_queue),
    db: AsyncSession = Depends(get_db),
):
    user = await user_service.create(db, data)

    # Enqueue async task (fire and forget)
    await queue.enqueue_job("send_email",
        to=user.email,
        subject="Welcome!",
        body="...",
        _queue_name="default",
        _defer_by=timedelta(seconds=5),  # optional delay
    )
    return user
```

```bash
# Run worker
arq workers.tasks.WorkerSettings

# With multiple processes
arq workers.tasks.WorkerSettings --processes 4
```

---

## Task Queues — Celery {#celery}

For more complex workflows, distributed tasks, or Django migrations.

```bash
pip install celery[redis] flower
```

```python
# celery_app.py
from celery import Celery
import asyncio

celery_app = Celery(
    "tasks",
    broker="redis://localhost:6379/1",
    backend="redis://localhost:6379/2",
    include=["workers.email_tasks", "workers.processing_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,     # acknowledge after task completes (prevents loss)
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,  # fair distribution
)

# Async task wrapper
def run_async(coro):
    """Run async code in a Celery task (synchronous context)"""
    return asyncio.get_event_loop().run_until_complete(coro)

@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def process_report(self, report_id: str):
    try:
        run_async(report_service.generate(report_id))
    except Exception as exc:
        raise self.retry(exc=exc)
```

---

## Streaming Responses {#streaming}

### JSON Lines Streaming (Modern Pattern)

For streaming a sequence of objects, declare `-> AsyncIterable[Model]` and use `yield`. FastAPI handles the serialization automatically via Pydantic (no manual wrapping needed).

```python
from collections.abc import AsyncIterable
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class Item(BaseModel):
    id: int
    name: str

# FastAPI streams each yielded object as a JSON line (NDJSON)
@app.get("/items/stream")
async def stream_items() -> AsyncIterable[Item]:
    async for item in fetch_items_from_db():
        yield item  # Pydantic serializes each in Rust; no memory accumulation
```

### Byte Streaming — Subclass StreamingResponse (Modern Pattern)

Prefer subclassing `StreamingResponse` over returning an instance directly. This keeps the endpoint signature clean and lets FastAPI handle the response class lifecycle.

```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

app = FastAPI()

class CSVStreamingResponse(StreamingResponse):
    media_type = "text/csv"

class PNGStreamingResponse(StreamingResponse):
    media_type = "image/png"

# PREFERRED — use response_class= and yield
@app.get("/export/users.csv", response_class=CSVStreamingResponse)
async def export_users():
    yield "id,email,name\n"
    async for user in stream_users():
        yield f"{user.id},{user.email},{user.name}\n"

@app.get("/image", response_class=PNGStreamingResponse)
def stream_image():
    with open_image() as img:
        yield from img  # sync yield — runs in thread pool (def, not async def)

# DO NOT DO THIS — returning StreamingResponse directly
@app.get("/items/")
async def bad():
    return StreamingResponse(generate(), media_type="text/csv")  # ❌
```

### StreamingResponse for Large Data (Manual — Legacy)

```python
from fastapi.responses import StreamingResponse
import csv
import io

@app.get("/export/users.csv")
async def export_users(db: AsyncSession = Depends(get_db)):
    async def generate_csv():
        # Stream CSV without loading all into memory
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["id", "email", "name", "created_at"])
        yield output.getvalue()
        output.seek(0)
        output.truncate()

        async for user in db.stream_scalars(select(User)):
            writer.writerow([user.id, user.email, user.full_name, user.created_at])
            yield output.getvalue()
            output.seek(0)
            output.truncate()

    return StreamingResponse(
        generate_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=users.csv"},
    )

# Stream large JSON array
@app.get("/stream/events")
async def stream_events():
    async def generate():
        yield '{"events": ['
        first = True
        async for event in db.stream_scalars(select(Event).order_by(Event.created_at)):
            if not first:
                yield ","
            yield event.to_json()
            first = False
        yield "]}"

    return StreamingResponse(generate(), media_type="application/json")
```

---

## WebSockets & SSE {#websockets-sse}

### WebSocket with Connection Manager

```python
from fastapi import WebSocket, WebSocketDisconnect
from typing import Any
import json

class ConnectionManager:
    def __init__(self):
        self.active: dict[str, list[WebSocket]] = {}  # room_id → connections

    async def connect(self, room_id: str, ws: WebSocket):
        await ws.accept()
        self.active.setdefault(room_id, []).append(ws)

    def disconnect(self, room_id: str, ws: WebSocket):
        self.active.get(room_id, []).remove(ws)
        if not self.active.get(room_id):
            del self.active[room_id]

    async def broadcast(self, room_id: str, message: Any):
        dead = []
        for ws in self.active.get(room_id, []):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(room_id, ws)

manager = ConnectionManager()

@app.websocket("/ws/{room_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    room_id: str,
    user: User = Depends(get_current_user_ws),
):
    await manager.connect(room_id, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            # Process message
            await manager.broadcast(room_id, {
                "from": user.username,
                "message": data["text"],
                "timestamp": datetime.now(UTC).isoformat(),
            })
    except WebSocketDisconnect:
        manager.disconnect(room_id, websocket)
        await manager.broadcast(room_id, {"system": f"{user.username} left"})
```

### Server-Sent Events (SSE) — Modern Pattern

Use `EventSourceResponse` from `fastapi.sse` (built into FastAPI). Plain objects are automatically JSON-serialized by Pydantic when you declare the return type.

```python
from collections.abc import AsyncIterable
from fastapi import FastAPI
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel

app = FastAPI()


class StatusUpdate(BaseModel):
    status: str
    progress: int


# Simple SSE — objects auto-serialized as `data:` fields via Pydantic
@app.get("/events/simple", response_class=EventSourceResponse)
async def stream_simple() -> AsyncIterable[StatusUpdate]:
    yield StatusUpdate(status="started", progress=0)
    await asyncio.sleep(1)
    yield StatusUpdate(status="processing", progress=50)
    await asyncio.sleep(1)
    yield StatusUpdate(status="done", progress=100)


# Full control — use ServerSentEvent for event name, id, retry, comment fields
@app.get("/events/stream", response_class=EventSourceResponse)
async def stream_events() -> AsyncIterable[ServerSentEvent]:
    yield ServerSentEvent(data={"status": "started"}, event="status", id="1")
    yield ServerSentEvent(data={"progress": 50}, event="progress", id="2", retry=3000)
    # Send pre-formatted string without JSON encoding
    yield ServerSentEvent(raw_data="plain log line", event="log")


# Real-time push with keep-alive
@app.get("/events/live", response_class=EventSourceResponse)
async def live_events(user_id: int) -> AsyncIterable[ServerSentEvent]:
    last_id = 0
    while True:
        events = await get_new_events(user_id, since=last_id)
        for event in events:
            last_id = event.id
            yield ServerSentEvent(data=event.model_dump(), event=event.type, id=str(event.id))

        # Keep-alive comment (no data, just prevents timeout)
        yield ServerSentEvent(comment="keepalive")
        await asyncio.sleep(15)
```

> Headers (`Cache-Control: no-cache`, `X-Accel-Buffering: no`) are set automatically by `EventSourceResponse`.

---

## Concurrency Patterns {#concurrency-patterns}

### asyncio.gather — Fan-Out Pattern

```python
@app.get("/multi-source")
async def multi_source(
    client: httpx.AsyncClient = Depends(get_http_client),
    db: AsyncSession = Depends(get_db),
):
    # Fetch from 3 sources simultaneously
    db_task = db.execute(select(Config))
    api1_task = client.get("https://api1.example.com/data")
    api2_task = client.get("https://api2.example.com/data")

    db_result, api1_resp, api2_resp = await asyncio.gather(
        db_task, api1_task, api2_task,
        return_exceptions=True
    )

    return {
        "config": db_result.scalars().all() if not isinstance(db_result, Exception) else None,
        "source1": api1_resp.json() if not isinstance(api1_resp, Exception) else None,
        "source2": api2_resp.json() if not isinstance(api2_resp, Exception) else None,
    }
```

### asyncio.TaskGroup (Python 3.11+)

```python
@app.get("/taskgroup")
async def taskgroup_example():
    results = {}
    async with asyncio.TaskGroup() as tg:
        # All tasks run concurrently; any exception cancels all others
        t1 = tg.create_task(fetch_users())
        t2 = tg.create_task(fetch_orders())
        t3 = tg.create_task(fetch_config())
    # Here all tasks completed (or TaskGroup raised ExceptionGroup)
    return {"users": t1.result(), "orders": t2.result(), "config": t3.result()}
```

### Semaphore — Rate Limiting Concurrent Operations

```python
# Limit to 5 concurrent external API calls
_semaphore = asyncio.Semaphore(5)

async def rate_limited_fetch(client: httpx.AsyncClient, url: str) -> dict:
    async with _semaphore:
        response = await client.get(url)
        return response.json()

@app.post("/batch-enrich")
async def batch_enrich(
    ids: list[str],
    client: httpx.AsyncClient = Depends(get_http_client),
):
    tasks = [rate_limited_fetch(client, f"https://api.example.com/{id}") for id in ids]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return results
```

---

## Profiling & Debugging Async {#profiling-async}

### Performance Timing Middleware

```python
import time
from fastapi import Request

@app.middleware("http")
async def timing_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    response.headers["X-Process-Time-Ms"] = f"{duration_ms:.2f}"

    # Log slow requests
    if duration_ms > 500:
        logger.warning(
            "Slow request",
            extra={
                "path": request.url.path,
                "method": request.method,
                "duration_ms": duration_ms,
            }
        )
    return response
```

### Profiling with py-spy

```bash
# Attach to running uvicorn process
py-spy top --pid $(pgrep -f uvicorn)

# Record flamegraph
py-spy record -o profile.svg --pid $(pgrep -f uvicorn) --duration 30
```

### async-profiler (asyncio debug mode)

```python
# Enable asyncio debug mode (finds blocking calls)
import asyncio
import logging

# In run.py
asyncio.get_event_loop().set_debug(True)
logging.getLogger("asyncio").setLevel(logging.DEBUG)

# Detects slow callbacks (>100ms threshold)
uvicorn.run("app.main:app", loop="asyncio")
```

### OpenTelemetry Tracing

```bash
pip install opentelemetry-sdk opentelemetry-instrumentation-fastapi opentelemetry-instrumentation-sqlalchemy
```

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

# Setup
provider = TracerProvider()
provider.add_span_processor(
    BatchSpanProcessor(OTLPSpanExporter(endpoint="http://jaeger:4317"))
)
trace.set_tracer_provider(provider)

# Auto-instrument
FastAPIInstrumentor.instrument_app(app)
SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
```
