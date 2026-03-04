# Official FastAPI Patterns & Best Practices

Canonical "do this, not that" rules from the official FastAPI skill. These override older conventions where they conflict.

## Table of Contents
1. [FastAPI CLI](#cli)
2. [Annotated — Always](#annotated)
3. [No Ellipsis](#no-ellipsis)
4. [Return Types vs response_model](#return-types)
5. [ORJSONResponse is Deprecated](#orjson-deprecated)
6. [Router Configuration](#routers)
7. [async def vs def — The Correct Rule](#async-vs-def)
8. [Dependency Injection Patterns](#di-patterns)
9. [No RootModel](#no-rootmodel)
10. [One HTTP Method Per Function](#one-method)
11. [Preferred Libraries (uv, Ruff, ty, Asyncer, SQLModel, HTTPX)](#libraries)

---

## FastAPI CLI {#cli}

Use the `fastapi` CLI instead of running uvicorn directly:

```bash
# Development (auto-reload)
fastapi dev

# Production
fastapi run

# With explicit path (when pyproject.toml entrypoint isn't set)
fastapi dev my_app/main.py
```

### Set entrypoint in `pyproject.toml` (preferred)

```toml
[tool.fastapi]
entrypoint = "my_app.main:app"
```

This avoids passing the path on every command. Use explicit path only when `pyproject.toml` isn't available or for standalone scripts.

---

## Annotated — Always {#annotated}

**Always use `Annotated` style** for all parameter declarations — Path, Query, Header, Cookie, Body, Form, File, Depends.

Reason: keeps function signatures valid Python outside FastAPI context, enables type reuse, works with IDE autocomplete correctly.

### Parameters

```python
from typing import Annotated
from fastapi import FastAPI, Path, Query

app = FastAPI()

# CORRECT
@app.get("/items/{item_id}")
async def read_item(
    item_id: Annotated[int, Path(ge=1, description="The item ID")],
    q: Annotated[str | None, Query(max_length=50)] = None,
):
    ...

# DO NOT DO THIS
@app.get("/items/{item_id}")
async def read_item(
    item_id: int = Path(ge=1, description="The item ID"),
    q: str | None = Query(default=None, max_length=50),
):
    ...
```

### Dependencies — Create Type Aliases

Create a named type alias for every reusable dependency. This makes injection sites readable and the alias reusable across routers.

```python
from typing import Annotated
from fastapi import Depends, FastAPI

app = FastAPI()


def get_current_user():
    return {"username": "johndoe"}


# Create an alias — reuse everywhere
CurrentUserDep = Annotated[dict, Depends(get_current_user)]


@app.get("/items/")
async def read_items(current_user: CurrentUserDep):
    ...

@app.get("/profile/")
async def read_profile(current_user: CurrentUserDep):
    ...

# DO NOT DO THIS
@app.get("/items/")
async def read_items(current_user: dict = Depends(get_current_user)):
    ...
```

---

## No Ellipsis {#no-ellipsis}

Do **not** use `...` as a default value for required parameters or Pydantic fields. It's not needed and not recommended.

```python
from typing import Annotated
from fastapi import FastAPI, Query
from pydantic import BaseModel, Field

class Item(BaseModel):
    name: str                       # required — no ellipsis needed
    description: str | None = None
    price: float = Field(gt=0)      # required — no ellipsis in Field()

app = FastAPI()

# CORRECT
@app.post("/items/")
async def create_item(
    item: Item,
    project_id: Annotated[int, Query()],  # required query param — no ellipsis
):
    ...

# DO NOT DO THIS
class Item(BaseModel):
    name: str = ...
    price: float = Field(..., gt=0)   # ellipsis not needed

@app.post("/items/")
async def create_item(item: Item, project_id: Annotated[int, Query(...)]):
    ...
```

---

## Return Types vs response_model {#return-types}

**Prefer return type annotations over `response_model=`** when possible. FastAPI uses the return type to validate, filter, document, and serialize via Pydantic's Rust engine — which is the fastest serialization path.

```python
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class Item(BaseModel):
    name: str
    description: str | None = None

# PREFERRED — return type drives serialization
@app.get("/items/me")
async def get_item() -> Item:
    return Item(name="Plumbus", description="All-purpose home device")
```

### When to use `response_model=` instead

Use `response_model=` only when the return type differs from the desired serialization/filtering type — typically for sensitive field stripping:

```python
from typing import Any
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class InternalItem(BaseModel):
    name: str
    description: str | None = None
    secret_key: str  # must not be exposed

class Item(BaseModel):
    name: str
    description: str | None = None

# Use response_model= to filter: return type is Any/InternalItem, serialize as Item
@app.get("/items/me", response_model=Item)
async def get_item() -> Any:
    item = InternalItem(name="Foo", description="Nice", secret_key="supersecret")
    return item  # secret_key is stripped by response_model
```

**Rule**: return type = `response_model=` → use return type. Return type ≠ serialization target → use `response_model=`.

---

## ORJSONResponse is Deprecated {#orjson-deprecated}

> **Do not use `ORJSONResponse` or `UJSONResponse`** — they are deprecated in modern FastAPI.

The reason: FastAPI now serializes responses using Pydantic's Rust-backed core when you declare a return type or `response_model`. This is equivalent performance to orjson without the extra dependency or response class.

```python
# DEPRECATED — do not use
from fastapi.responses import ORJSONResponse

app = FastAPI(default_response_class=ORJSONResponse)  # ❌

@app.get("/fast", response_class=ORJSONResponse)      # ❌
async def fast(): ...

# CORRECT — declare return type; Pydantic serializes in Rust automatically
@app.get("/items/")
async def list_items() -> list[Item]:                 # ✅
    return items
```

If you have `default_response_class=ORJSONResponse` in existing code, remove it and add return types instead.

---

## Router Configuration {#routers}

Set `prefix`, `tags`, and shared `dependencies` on the `APIRouter` itself — not in `include_router()`.

```python
from fastapi import APIRouter, FastAPI, Depends

app = FastAPI()

# CORRECT — prefix and tags on the router
router = APIRouter(
    prefix="/items",
    tags=["items"],
    dependencies=[Depends(require_auth)],  # applied to all routes in router
)

@router.get("/")
async def list_items():
    return []

app.include_router(router)  # clean — no parameters here

# DO NOT DO THIS — parameters on include_router()
router = APIRouter()

@router.get("/")
async def list_items():
    return []

app.include_router(router, prefix="/items", tags=["items"])  # ❌
```

**Exception**: `include_router()` parameters are fine for dynamic configuration (e.g., adding a router multiple times under different prefixes).

---

## async def vs def — The Correct Rule {#async-vs-def}

Use `async def` **only** when calling async/awaitable code. Use plain `def` when calling blocking/sync code or **when in doubt**.

```python
from fastapi import FastAPI

app = FastAPI()

# Use async def when awaiting async libraries
@app.get("/async-items/")
async def read_async_items():
    data = await some_async_library.fetch_items()  # awaitable call
    return data

# Use def when calling blocking code — FastAPI runs it in a threadpool automatically
@app.get("/items/")
def read_items():
    data = some_blocking_library.fetch_items()  # blocking — fine in def
    return data
```

**Why this matters**: If you put blocking code inside `async def`, it blocks the entire event loop and kills concurrency for all requests. FastAPI detects `def` path operations and runs them in a thread pool automatically, so they never block the event loop.

```python
# BAD — blocking call inside async def blocks ALL requests
@app.get("/bad/")
async def bad_endpoint():
    import time
    time.sleep(2)          # blocks event loop
    data = requests.get(url)  # blocks event loop
    return data

# GOOD — same logic in def, runs in thread pool
@app.get("/good/")
def good_endpoint():
    import time
    time.sleep(2)          # runs in thread pool, event loop stays free
    data = requests.get(url)  # fine
    return data
```

The same rule applies to dependencies — use `def` for blocking dependencies.

When you need to call async code from sync, or sync code from async, use **Asyncer** (see [Preferred Libraries](#libraries)).

---

## Dependency Injection Patterns {#di-patterns}

### When to use dependencies

- Logic can't be declared in Pydantic validation (requires additional processing)
- Depends on external resources (DB, Redis, HTTP client)
- Needs cleanup after request (`yield`)
- Shared across multiple endpoints
- Needs to fail early (auth check, permission check)

### Dependency Scope

```python
from typing import Annotated
from fastapi import Depends, FastAPI

app = FastAPI()

# Default scope: "request" — cleanup runs AFTER response is sent
def get_db():
    db = DBSession()
    try:
        yield db
    finally:
        db.close()  # called after response sent to client

DBDep = Annotated[DBSession, Depends(get_db)]

# scope="function" — cleanup runs BEFORE response is sent (rare, specific use case)
def get_username():
    try:
        yield "Rick"
    finally:
        print("Cleanup before response is sent")  # runs while response is being built

UserNameDep = Annotated[str, Depends(get_username, scope="function")]
```

### Class Dependencies — Use Wrapper Function + Dataclass

Avoid using a class directly as a `Depends()` target. Instead, wrap it in a function that returns an instance, and use `@dataclass` for the data structure.

```python
from dataclasses import dataclass
from typing import Annotated
from fastapi import Depends, FastAPI

app = FastAPI()

# CORRECT — dataclass + factory function
@dataclass
class DatabasePaginator:
    offset: int = 0
    limit: int = 100
    q: str | None = None

    def get_page(self) -> dict:
        return {"offset": self.offset, "limit": self.limit, "q": self.q, "items": []}


def get_db_paginator(
    offset: int = 0, limit: int = 100, q: str | None = None
) -> DatabasePaginator:
    return DatabasePaginator(offset=offset, limit=limit, q=q)


PaginatorDep = Annotated[DatabasePaginator, Depends(get_db_paginator)]


@app.get("/items/")
async def read_items(paginator: PaginatorDep):
    return paginator.get_page()


# DO NOT DO THIS — class as Depends() target directly
class DatabasePaginator:
    def __init__(self, offset: int = 0, limit: int = 100, q: str | None = None):
        ...

@app.get("/items/")
async def read_items(paginator: Annotated[DatabasePaginator, Depends()]):  # ❌
    ...
```

---

## No RootModel {#no-rootmodel}

Do **not** use `Pydantic.RootModel`. FastAPI creates a `TypeAdapter` internally for annotated types, so RootModel is unnecessary and adds complexity.

```python
from typing import Annotated
from fastapi import Body, FastAPI
from pydantic import Field

app = FastAPI()

# CORRECT — use Annotated type directly
@app.post("/items/")
async def create_items(
    items: Annotated[list[int], Field(min_length=1), Body()]
):
    return items

# DO NOT DO THIS — RootModel is unnecessary
from pydantic import Field, RootModel

class ItemList(RootModel[Annotated[list[int], Field(min_length=1)]]):
    pass

@app.post("/items/")
async def create_items(items: ItemList):  # ❌
    return items
```

---

## One HTTP Method Per Function {#one-method}

**One function per HTTP operation.** Never multiplex multiple methods through `api_route()`.

```python
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class Item(BaseModel):
    name: str

# CORRECT — one function per operation
@app.get("/items/")
async def list_items():
    return []

@app.post("/items/")
async def create_item(item: Item):
    return item

# DO NOT DO THIS
@app.api_route("/items/", methods=["GET", "POST"])  # ❌
async def handle_items(request: Request):
    if request.method == "GET":
        return []
    ...
```

---

## Preferred Libraries {#libraries}

### Package Management: uv

Use `uv` when available. It's significantly faster than pip and handles virtual environments automatically.

```bash
uv add fastapi
uv add --dev pytest pytest-asyncio httpx
uv run fastapi dev
```

### Linting & Formatting: Ruff

```bash
uv add --dev ruff

# Enable FastAPI-specific Ruff rules in pyproject.toml
[tool.ruff.lint]
select = ["E", "F", "I", "FAST"]  # FAST = FastAPI rules
```

### Type Checking: ty

```bash
uv add --dev ty
ty check
```

### Async/Sync Bridge: Asyncer (preferred over asyncio/AnyIO)

When you need to run blocking code inside `async def`, or async code inside `def`:

```bash
uv add asyncer
```

```python
from asyncer import asyncify, syncify

# Run blocking sync code inside async function
@app.get("/items/")
async def read_items():
    result = await asyncify(some_blocking_function)(name="World")
    return {"result": result}

# Run async code inside sync function (dependency, background task, etc.)
@app.get("/sync-items/")
def read_items_sync():
    result = syncify(some_async_function)(name="World")
    return {"result": result}
```

> **Prefer Asyncer over** `asyncio.to_thread()`, `loop.run_in_executor()`, or direct AnyIO usage. It's cleaner and handles edge cases.

### SQL Databases: SQLModel (preferred over SQLAlchemy)

SQLModel combines SQLAlchemy + Pydantic — one model for both DB and API schema.

```python
from sqlmodel import Field, Session, SQLModel, create_engine, select

class Item(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    price: float = Field(gt=0)

# Use as both ORM model and Pydantic schema
class ItemCreate(SQLModel):
    name: str
    price: float

class ItemRead(SQLModel):
    id: int
    name: str
    price: float
```

### HTTP Client: HTTPX (preferred over Requests)

```python
import httpx
from fastapi import FastAPI

app = FastAPI()

# Async (preferred inside async def)
@app.get("/proxy/")
async def proxy():
    async with httpx.AsyncClient() as client:
        response = await client.get("https://api.example.com/data")
        return response.json()

# Sync (inside def endpoints or testing)
def fetch_data():
    with httpx.Client() as client:
        return client.get("https://api.example.com/data").json()
```

Use a singleton `httpx.AsyncClient` via lifespan for production (avoids opening a new connection per request):

```python
from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI

http_client: httpx.AsyncClient = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client
    http_client = httpx.AsyncClient(timeout=10.0)
    yield
    await http_client.aclose()

app = FastAPI(lifespan=lifespan)

# In endpoints — use the singleton
async def get_http_client() -> httpx.AsyncClient:
    return http_client

HTTPClientDep = Annotated[httpx.AsyncClient, Depends(get_http_client)]
```
