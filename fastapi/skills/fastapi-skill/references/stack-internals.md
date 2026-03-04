# FastAPI Stack Internals — Starlette, Pydantic, FastAPI

## Table of Contents
1. [The Layered Architecture](#layered-architecture)
2. [Starlette Internals](#starlette-internals)
3. [Pydantic v2 Internals](#pydantic-v2-internals)
4. [FastAPI Dependency Injection](#fastapi-dependency-injection)
5. [ASGI Lifecycle & Lifespan](#asgi-lifecycle)
6. [Request/Response Flow](#request-response-flow)
7. [Performance Implications](#performance-implications)

---

## Layered Architecture

```
┌────────────────────────────────────────────┐
│                  FastAPI                   │  ← Path operations, DI, OpenAPI gen
│  (Starlette subclass + Pydantic integration)│
├────────────────────────────────────────────┤
│                 Starlette                  │  ← Routing, middleware, ASGI, WebSockets
├────────────────────────────────────────────┤
│              Pydantic v2 (Rust)            │  ← Validation, serialization, JSON schema
├────────────────────────────────────────────┤
│          ASGI Server (Uvicorn/Gunicorn)    │  ← HTTP parsing, event loop management
└────────────────────────────────────────────┘
```

FastAPI **is** Starlette — `class FastAPI(Starlette)`. Everything Starlette supports (WebSockets, Server-Sent Events, mounting sub-applications, static files) is available directly.

---

## Starlette Internals

### Router and Routes

Starlette's `Router` maintains a list of `Route` objects. When a request comes in:
1. Router iterates routes and calls each route's `matches()` method
2. First matching route wins
3. Route calls the endpoint (or next middleware)

FastAPI wraps Starlette's `Route` to inject Pydantic validation before calling the endpoint function.

### Middleware Stack

Middleware is composed as a stack of ASGI callables. Each middleware wraps the next:

```python
# Internal representation
app = GZipMiddleware(
    CORSMiddleware(
        HTTPSRedirectMiddleware(
            actual_app
        )
    )
)
```

**Middleware registration order** — last registered = outermost:
```python
app.add_middleware(GZipMiddleware)       # innermost (runs last on request, first on response)
app.add_middleware(CORSMiddleware)       # middle
app.add_middleware(HTTPSRedirectMiddleware)  # outermost (runs first on request, last on response)
```

**Critical**: Add GZip AFTER other middlewares, so responses are compressed after all processing.

### Background Tasks

Starlette's `BackgroundTasks` uses a `BackgroundTask` wrapper. Tasks run in `Response.background` after the response bytes are sent:

```python
# Starlette source (simplified)
class Response:
    async def __call__(self, scope, receive, send):
        await send({"type": "http.response.start", ...})
        await send({"type": "http.response.body", ...})
        if self.background is not None:
            await self.background()  # runs AFTER response sent
```

### WebSockets

Starlette provides `WebSocket` class directly. FastAPI exposes it:
```python
from fastapi import WebSocket

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    while True:
        data = await websocket.receive_text()
        await websocket.send_text(f"Echo: {data}")
```

For production WebSockets, use connection managers to track active connections.

---

## Pydantic v2 Internals

Pydantic v2 rewrote the core in Rust (`pydantic-core`), giving 5-50x speedup over v1.

### Model Compilation

When you define a `BaseModel`, Pydantic v2:
1. Inspects all `ClassVar`, `Field`, `Annotated` declarations at **class definition time**
2. Compiles a **validation schema** (Rust struct)
3. Compiles a **serialization schema** (Rust struct)

This means model validation/serialization is done by compiled Rust code at runtime — zero Python overhead in the hot path.

### Validation vs Serialization

```python
from pydantic import BaseModel, Field
from typing import Annotated

class Item(BaseModel):
    name: str
    price: Annotated[float, Field(gt=0, le=10000)]
    tags: list[str] = []
```

- **Validation** (input → Python): `Item.model_validate({"name": "foo", "price": 9.99})`
- **Serialization** (Python → output): `item.model_dump()`, `item.model_dump_json()`

### ConfigDict Options (v2)

```python
from pydantic import BaseModel, ConfigDict

class Config(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,        # ORM mode: read from .attr not ['key']
        populate_by_name=True,       # allow field name OR alias
        str_strip_whitespace=True,   # auto-strip string whitespace
        str_min_length=1,            # minimum string length globally
        use_enum_values=True,        # store enum value not enum member
        validate_default=True,       # validate default values too
        frozen=True,                 # make model immutable (hashable)
        arbitrary_types_allowed=True, # allow non-Pydantic types
        json_schema_extra={          # add to OpenAPI schema
            "example": {"name": "Foo"}
        }
    )
```

### Field Types and Annotated Pattern (v2)

```python
from pydantic import BaseModel, Field, EmailStr, HttpUrl
from typing import Annotated

# Preferred v2 pattern: Annotated + Field
class User(BaseModel):
    id: Annotated[int, Field(gt=0, description="Unique user identifier")]
    email: Annotated[EmailStr, Field(description="User email")]
    name: Annotated[str, Field(min_length=1, max_length=100)]
    score: Annotated[float, Field(ge=0.0, le=100.0, default=0.0)]
    tags: Annotated[list[str], Field(default_factory=list, max_length=20)]
    website: HttpUrl | None = None
```

### Validators

```python
from pydantic import BaseModel, field_validator, model_validator
from typing import Self

class Order(BaseModel):
    quantity: int
    price: float
    discount: float = 0.0
    total: float = 0.0

    @field_validator('quantity')
    @classmethod
    def quantity_must_be_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError('quantity must be positive')
        return v

    @field_validator('discount')
    @classmethod
    def discount_must_be_percentage(cls, v: float) -> float:
        if not 0 <= v <= 1:
            raise ValueError('discount must be between 0 and 1')
        return v

    @model_validator(mode='after')
    def calculate_total(self) -> Self:
        self.total = self.quantity * self.price * (1 - self.discount)
        return self
```

### Computed Fields

```python
from pydantic import BaseModel, computed_field

class Rectangle(BaseModel):
    width: float
    height: float

    @computed_field
    @property
    def area(self) -> float:
        return self.width * self.height
```

### Discriminated Unions (Polymorphism)

```python
from typing import Annotated, Literal, Union
from pydantic import BaseModel, Field

class Cat(BaseModel):
    pet_type: Literal['cat']
    meow_volume: int

class Dog(BaseModel):
    pet_type: Literal['dog']
    bark_loudness: str

Pet = Annotated[Union[Cat, Dog], Field(discriminator='pet_type')]

class Owner(BaseModel):
    pet: Pet
```

---

## FastAPI Dependency Injection

FastAPI's DI system runs dependencies in a DAG (directed acyclic graph), cached per request.

### Dependency Scopes

```python
from fastapi import Depends
from functools import lru_cache

# REQUEST-scoped (default): runs once per request
async def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# APPLICATION-scoped: runs once at startup
@lru_cache
def get_settings():
    return Settings()

# CLASS-based dependency
class Paginator:
    def __init__(self, skip: int = 0, limit: int = 100):
        self.skip = skip
        self.limit = limit

@app.get("/items/")
async def list_items(
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    page: Paginator = Depends(Paginator),
):
    ...
```

### Dependency Caching

FastAPI caches dependencies within a single request. The same dependency instance is reused if declared multiple times:

```python
# Both endpoints share the same 'get_db' instance for one request
async def get_current_user(db = Depends(get_db)): ...
async def log_request(db = Depends(get_db)): ...
```

To disable caching: `Depends(get_db, use_cache=False)`

### Security Dependencies

```python
from fastapi.security import (
    OAuth2PasswordBearer,
    OAuth2PasswordRequestForm,
    APIKeyHeader,
    HTTPBasic,
    HTTPBearer,
)

# OAuth2 Bearer
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

# API Key header
api_key_header = APIKeyHeader(name="X-API-Key")

# HTTP Bearer
http_bearer = HTTPBearer()
```

---

## ASGI Lifecycle

### Lifespan (Modern Approach, FastAPI 0.93+)

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: runs before first request
    print("Starting up...")
    db_pool = await create_db_pool()
    redis = await aioredis.create_redis_pool(...)
    app.state.db = db_pool
    app.state.redis = redis

    yield  # App is running

    # Shutdown: runs after last request
    print("Shutting down...")
    await db_pool.close()
    redis.close()
    await redis.wait_closed()

app = FastAPI(lifespan=lifespan)
```

### Accessing App State in Routes

```python
from fastapi import Request

@app.get("/data")
async def get_data(request: Request):
    db = request.app.state.db
    return await db.fetch("SELECT ...")
```

---

## Request/Response Flow

```
Client Request
    │
    ▼
ASGI Server (Uvicorn)
    │
    ▼
Middleware Stack (outermost first)
    │  - HTTPSRedirect, CORS, GZip, custom middleware
    ▼
FastAPI Router
    │
    ▼
Path Operation Dependencies (resolved in DAG order)
    │  - Security, DB sessions, pagination, current user
    ▼
Request Body Validation (Pydantic)
    │  - JSON parsing → Pydantic model validation
    │  - 422 if validation fails
    ▼
Path Operation Function (your code)
    │
    ▼
Response Model Serialization (Pydantic)
    │  - Filter fields, apply response_model
    ▼
Response (JSON bytes)
    │
    ▼
Middleware Stack (innermost first, return path)
    │
    ▼
Background Tasks
    │
    ▼
Client Response
```

---

## Performance Implications

### async def vs def

| | `async def` | `def` |
|---|---|---|
| Runs in | Event loop | Thread pool (anyio.to_thread) |
| Best for | I/O bound (DB, HTTP, file) | CPU bound (ML inference, image processing) |
| Blocking risk | Never block — use await | Safe to block |
| Overhead | None | Thread pool overhead |

**Never** mix blocking calls in `async def`:
```python
# BAD: blocks event loop
@app.get("/bad")
async def bad():
    time.sleep(1)        # blocks entire server
    result = requests.get(url)  # blocking HTTP

# GOOD: non-blocking
@app.get("/good")
async def good():
    await asyncio.sleep(1)
    async with httpx.AsyncClient() as client:
        result = await client.get(url)
```

### Response Model Optimization

```python
# Avoid serializing unused fields
@app.get("/items/", response_model=ItemRead)
async def list_items(
    response_model_exclude_unset=True,  # skip fields not set by user
    response_model_exclude_none=True,   # skip None fields
):
    ...

# Use JSONResponse for pre-serialized data
from fastapi.responses import JSONResponse, ORJSONResponse

# ORJSONResponse: ~10x faster than default JSONResponse
# Install: pip install orjson
@app.get("/fast", response_class=ORJSONResponse)
async def fast_endpoint():
    return {"data": large_list}
```

### Connection Pool Tuning

For SQLAlchemy async engine:
```python
engine = create_async_engine(
    DATABASE_URL,
    pool_size=10,          # base connections (= expected concurrent requests / workers)
    max_overflow=20,        # burst capacity
    pool_timeout=30,        # wait time before raising error
    pool_recycle=3600,      # recycle connections hourly
    pool_pre_ping=True,     # validate connections before use
)
```

Formula: `pool_size = (concurrent_requests / uvicorn_workers)`

### Gunicorn + Uvicorn Workers

For production, run Uvicorn workers managed by Gunicorn:
```bash
gunicorn app.main:app \
  --workers $((2 * $(nproc) + 1)) \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --timeout 120 \
  --graceful-timeout 30 \
  --max-requests 1000 \
  --max-requests-jitter 50
```

- `2 * CPU + 1` workers for I/O-bound APIs
- `max-requests` prevents memory leaks by recycling workers
- `max-requests-jitter` staggers recycling to avoid thundering herd
