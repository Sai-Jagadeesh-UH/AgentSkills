# Package Internals — FastAPI 0.135, Starlette 0.52, Pydantic 2.12, Uvicorn

> Source-level analysis from installed packages (Python 3.13 environment)
> Versions: FastAPI 0.135.1 | Starlette 0.52.1 | Pydantic 2.12.5 | Pydantic-Core 2.41.5 | AnyIO 4.12.1

## Table of Contents
1. [FastAPI Class Hierarchy](#fastapi-hierarchy)
2. [Dependency Injection Internals](#di-internals)
3. [Request/Response Flow (Complete)](#request-response-flow)
4. [Parameter System](#parameter-system)
5. [Security Schemes Available](#security-schemes)
6. [Starlette Middleware Stack Build](#middleware-build)
7. [Background Task Execution](#background-task-execution)
8. [Pydantic Core (Rust Engine)](#pydantic-core)
9. [JSON Encoding Chain](#json-encoding)
10. [Performance-Critical Patterns](#performance-patterns)
11. [Key File Map](#key-file-map)

---

## FastAPI Class Hierarchy {#fastapi-hierarchy}

```
fastapi.FastAPI (applications.py)
└── starlette.Starlette (starlette/applications.py)
    └── ASGI callable
```

FastAPI is literally a subclass of Starlette. Everything in Starlette is available in FastAPI unchanged.

```python
# FastAPI.__init__ signature (key params)
class FastAPI(Starlette):
    def __init__(
        self,
        *,
        debug: bool = False,
        title: str = "FastAPI",
        summary: str | None = None,
        description: str = "",
        version: str = "0.1.0",
        openapi_url: str | None = "/openapi.json",
        openapi_tags: list[dict] | None = None,
        servers: list[dict] | None = None,
        dependencies: Sequence[Depends] | None = None,
        default_response_class: type[Response] = Default(JSONResponse),
        redirect_slashes: bool = True,
        docs_url: str | None = "/docs",
        redoc_url: str | None = "/redoc",
        swagger_ui_oauth2_redirect_url: str | None = "/docs/oauth2-redirect",
        lifespan: Lifespan[AppType] | None = None,
        terms_of_service: str | None = None,
        contact: dict | None = None,
        license_info: dict | None = None,
        # ... routes, middleware, exception_handlers (inherited from Starlette)
    )
```

---

## Dependency Injection Internals {#di-internals}

### The Dependant Dataclass (from source)

```python
# fastapi/dependencies/models.py
@dataclass
class Dependant:
    # Parameter categorization
    path_params: list[ModelField]
    query_params: list[ModelField]
    header_params: list[ModelField]
    cookie_params: list[ModelField]
    body_params: list[ModelField]

    # Nested dependencies (recursive tree)
    dependencies: list[Dependant]

    # Callable info
    name: str | None = None
    call: Callable | None = None

    # Special parameter slots
    request_param_name: str | None = None    # Request type hint
    response_param_name: str | None = None  # Response type hint
    background_tasks_param_name: str | None = None  # BackgroundTasks
    security_scopes_param_name: str | None = None   # SecurityScopes

    # Caching
    use_cache: bool = True
    scope: Literal["function", "request"] | None = None

    @cached_property
    def cache_key(self) -> tuple:
        """Key for request-scoped dependency cache"""
        return (self.call, tuple(sorted(self.oauth_scopes or [])), self.computed_scope or "")
```

### How DI Resolves Parameters (from utils.py)

FastAPI inspects function signatures to determine parameter sources:

| Annotation + Marker | Source |
|---|---|
| `str` + `Query()` | Query string |
| `str` + `Path()` | URL path segment |
| `str` + `Header()` | HTTP header |
| `str` + `Cookie()` | Cookie |
| `BaseModel` + `Body()` | Request body |
| `UploadFile` + `File()` | Multipart upload |
| `str` + `Form()` | Form field |
| `Depends(func)` | Sub-dependency |
| `Request` type hint | Raw Starlette Request |
| `Response` type hint | Response object (for mutation) |
| `BackgroundTasks` type hint | Background task manager |
| `SecurityScopes` type hint | OAuth2 scope collector |

### Dependency Caching

```python
# Within a single request, same dependency is called once
# Cache key = (callable, scopes_tuple, scope_str)

# Example: if both endpoints declare Depends(get_db),
# get_db() runs ONCE per request, not twice
async def get_items(db = Depends(get_db)): ...
async def get_current_user(db = Depends(get_db)): ...

# Both receive the SAME AsyncSession object for that request
# Disable with use_cache=False
async def get_db_fresh(db = Depends(get_db, use_cache=False)): ...
```

### AsyncExitStack Pattern (Critical for yield deps)

```python
# fastapi/routing.py — actual implementation
async def request_response(func):
    async def app(scope, receive, send):
        request = Request(scope, receive, send)
        async with AsyncExitStack() as request_stack:
            scope["fastapi_inner_astack"] = request_stack
            async with AsyncExitStack() as function_stack:
                scope["fastapi_function_astack"] = function_stack
                response = await func(request)  # runs endpoint + all deps
            await response(scope, receive, send)  # send response
        # Here: request_stack cleanup runs (yield deps, context managers)
```

This ensures `yield` dependencies are always cleaned up, even on exceptions.

---

## Request/Response Flow (Complete) {#request-response-flow}

```
ASGI Server (Uvicorn)
    │
    ▼
scope["app"] = FastAPI instance
    │
    ▼
FastAPI/Starlette middleware_stack (built lazily on first request):
    │
    ├─► ServerErrorMiddleware (outermost — catches all 500s)
    │
    ├─► User Middleware (reversed order of add_middleware() calls)
    │   └─ CORS, GZip, Custom...
    │
    ├─► ExceptionMiddleware (handles HTTPException → JSON error)
    │
    └─► Router.handle()
            │
            ▼
        Route.matches() → regex check on path
            │
            ▼ (match found)
        APIRoute.__call__()
            │
            ▼
        FastAPI request_response() wrapper
            │
            ├─ Create request_astack (AsyncExitStack)
            ├─ Create function_astack (AsyncExitStack)
            │
            ├─ solve_dependencies():
            │   ├─ Extract path params (from regex groups)
            │   ├─ Extract query params (from scope["query_string"])
            │   ├─ Parse headers (from scope["headers"])
            │   ├─ Parse cookies
            │   ├─ Read + validate request body (Pydantic)
            │   └─ Execute sub-dependencies (recursive, cached)
            │
            ├─ Execute endpoint function
            │
            ├─ Validate return value with response_model (Pydantic)
            │
            ├─ Serialize: model_dump_json() → bytes
            │
            └─ Send JSONResponse (status + headers + body bytes)
                    │
                    ▼
                Execute BackgroundTasks (after response sent)
                    │
                    ▼
                Cleanup AsyncExitStacks (yield dependencies)
```

---

## Parameter System {#parameter-system}

### Parameter Class Hierarchy (from params.py)

```
pydantic.fields.FieldInfo
└── Param
    ├── Path    (in_=ParamTypes.path)
    ├── Query   (in_=ParamTypes.query)
    ├── Header  (in_=ParamTypes.header)  # has convert_underscores=True
    └── Cookie  (in_=ParamTypes.cookie)
└── Body
    ├── Form    (media_type="application/x-www-form-urlencoded")
    └── File    (media_type="multipart/form-data")

# Standalone (not FieldInfo subclass)
Depends (dataclass, frozen=True)
    use_cache: bool = True
    scope: Literal["function", "request"] | None = None

Security(Depends)
    scopes: Sequence[str] | None = None
```

### Complete Field Constraints (from FieldInfo source)

```python
Field(
    default=...,            # PydanticUndefined for required
    default_factory=None,   # Callable to generate default
    alias=None,             # Input alias (validation)
    serialization_alias=None,  # Output alias (serialization)
    title=None,             # OpenAPI title
    description=None,       # OpenAPI description
    examples=None,          # list of examples
    gt=None,                # > (greater than)
    ge=None,                # >= (greater than or equal)
    lt=None,                # < (less than)
    le=None,                # <= (less than or equal)
    min_length=None,        # min string/sequence length
    max_length=None,        # max string/sequence length
    pattern=None,           # regex pattern (for strings)
    discriminator=None,     # tagged union discriminator
    deprecated=None,        # bool | str | Deprecated
    json_schema_extra=None, # extra JSON schema properties
    frozen=None,            # immutable field
    validate_default=None,  # validate defaults
    repr=True,              # include in __repr__
    exclude=None,           # exclude from model_dump()
    include=None,           # include only these (model_dump)
    max_digits=None,        # for Decimal
    decimal_places=None,    # for Decimal
)
```

---

## Security Schemes Available {#security-schemes}

All from `fastapi.security` (re-exported from Starlette + FastAPI):

```python
from fastapi.security import (
    # API Key variants
    APIKeyHeader,       # X-API-Key header
    APIKeyQuery,        # ?api_key= query parameter
    APIKeyCookie,       # api_key cookie

    # HTTP Auth
    HTTPBasic,          # Username/password (Basic Auth)
    HTTPBearer,         # Bearer token (raw, no validation)
    HTTPDigest,         # HTTP Digest Auth

    # OAuth2
    OAuth2PasswordBearer,              # Bearer token with tokenUrl
    OAuth2AuthorizationCodeBearer,     # Auth code flow
    OAuth2PasswordRequestForm,         # Form: username + password + scope
    OAuth2PasswordRequestFormStrict,   # Strict: requires grant_type field

    # OpenID Connect
    OpenIdConnect,      # OIDC discovery URL

    # Scope injection
    SecurityScopes,     # Injects merged OAuth2 scopes
)
```

### SecurityScopes — Aggregating Scopes Across Dependencies

```python
from fastapi.security import SecurityScopes

# Scopes are accumulated across the dependency chain
async def get_current_user(
    security_scopes: SecurityScopes,  # injected automatically
    token: str = Depends(oauth2_scheme),
):
    # security_scopes.scopes = ["users:read", "items:write"] (merged)
    # Validate token has all required scopes
    for scope in security_scopes.scopes:
        if scope not in token_scopes:
            raise HTTPException(403, f"Missing scope: {scope}")

@app.get("/items/", dependencies=[Security(get_current_user, scopes=["items:read"])])
async def list_items(): ...
```

---

## Starlette Middleware Stack Build {#middleware-build}

From `starlette/applications.py`:

```python
def build_middleware_stack(self) -> ASGIApp:
    """
    Starlette builds the stack in this FIXED order:
    1. ServerErrorMiddleware  (outermost — catches 500s, shows debug tracebacks)
    2. User middleware        (in REVERSE order of registration)
    3. ExceptionMiddleware    (innermost — converts HTTPException to JSON)
    4. Router                 (final ASGI app)
    """
    middleware = [
        Middleware(ServerErrorMiddleware, handler=error_handler, debug=self.debug),
        *self.user_middleware,  # reversed by build logic
        Middleware(ExceptionMiddleware, handlers=exc_handlers, debug=self.debug),
    ]
    app = self.router
    for cls, args, kwargs in reversed(middleware):
        app = cls(app, *args, **kwargs)
    return app
```

**Critical insight**: The stack is built **lazily** on the first request, then cached in `self.middleware_stack`. This means `add_middleware()` after the first request has no effect.

**Middleware ordering (from add_middleware calls):**
```python
# If you call:
app.add_middleware(A)  # stored as [A]
app.add_middleware(B)  # stored as [A, B]

# Stack becomes:
# ServerErrorMiddleware → B → A → ExceptionMiddleware → Router
# Request flows: B first, then A
# Response flows: A first, then B
```

---

## Background Task Execution {#background-task-execution}

From `starlette/background.py`:

```python
class BackgroundTask:
    def __init__(self, func, *args, **kwargs):
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.is_async = is_async_callable(func)  # from anyio

    async def __call__(self) -> None:
        if self.is_async:
            await self.func(*self.args, **self.kwargs)
        else:
            # Sync functions run in thread pool automatically!
            await run_in_threadpool(self.func, *self.args, **self.kwargs)

class BackgroundTasks(BackgroundTask):
    def __init__(self, tasks=None):
        self.tasks = list(tasks or [])

    def add_task(self, func, *args, **kwargs):
        self.tasks.append(BackgroundTask(func, *args, **kwargs))

    async def __call__(self) -> None:
        for task in self.tasks:
            await task()  # sequential — tasks run one after another!
```

**Key insights:**
1. **Sync functions** in BackgroundTasks run in thread pool automatically — no need for `asyncio.to_thread`
2. Tasks run **sequentially** (not parallel) — one finishes before next starts
3. Tasks execute **after** response bytes sent, but **within** connection lifetime
4. **No retry mechanism** — if a task fails, the error is logged but response already sent

---

## Pydantic Core (Rust Engine) {#pydantic-core}

```
pydantic_core/
├── _pydantic_core.cpython-313-x86_64-linux-gnu.so  ← Rust compiled binary
├── core_schema.py   ← Python wrappers for Rust schema types
└── __init__.py      ← Exports: ValidationError, PydanticUndefined, etc.
```

### How Pydantic v2 Works

At class definition time:
1. Python inspects class body (annotations, fields)
2. Builds a **core schema** (Python dict describing types and validators)
3. Passes schema to Rust via `SchemaValidator(core_schema)`
4. Rust compiles it into a native validation function

At validation time:
1. `Model.model_validate(data)` calls Rust directly
2. **Zero Python overhead** in the hot validation path
3. Returns Python objects

```python
# What happens internally when you define a model:
class User(BaseModel):
    email: EmailStr
    name: str

# Pydantic generates something like:
_schema = {
    "type": "model",
    "cls": User,
    "fields_schema": {
        "email": {"type": "str", "validators": [email_validator]},
        "name": {"type": "str"},
    }
}
_validator = SchemaValidator(_schema)  # compiled to Rust

# At validation time:
User.model_validate({"email": "a@b.com", "name": "Alice"})
# → _validator.validate_python({"email": "a@b.com", "name": "Alice"})
# → Rust code runs, returns Python dict → model instance
```

### TypeAdapter — Validate Arbitrary Types

```python
from pydantic import TypeAdapter

# Validate without a model class
ta = TypeAdapter(list[int])
result = ta.validate_python(["1", "2", "3"])  # [1, 2, 3]

# Validate JSON directly (fastest path)
result = ta.validate_json('[1, 2, 3]')

# Use for dynamic schemas
from typing import Annotated
PositiveInt = Annotated[int, Field(gt=0)]
ta = TypeAdapter(PositiveInt)
ta.validate_python(-1)  # raises ValidationError
```

---

## JSON Encoding Chain {#json-encoding}

FastAPI uses a layered approach to JSON serialization (from `encoders.py`):

```python
# ENCODERS_BY_TYPE — fallback for types not handled by Pydantic
ENCODERS_BY_TYPE = {
    bytes: lambda o: o.decode(),
    datetime.date: isoformat,
    datetime.datetime: isoformat,
    datetime.time: isoformat,
    datetime.timedelta: lambda td: td.total_seconds(),
    Decimal: decimal_encoder,        # str(v) if no decimal places
    Enum: lambda o: o.value,
    frozenset: list,
    deque: list,
    IPv4Address: str,
    IPv6Address: str,
    UUID: str,                       # str(uuid)
    Path: str,
    Pattern: lambda o: o.pattern,
    SecretStr: str,
    SecretBytes: str,
}
```

**Modern serialization path (Pydantic v2):**
```python
# When using response_model, FastAPI uses:
response_model.model_validate(return_value)  # validate
.model_dump_json()  # → bytes directly from Rust

# ORJSONResponse is now largely unnecessary — Pydantic's
# model_dump_json() already uses a Rust serializer internally
```

---

## Performance-Critical Patterns {#performance-patterns}

### 1. Path Compilation (startup-time, not per-request)

```python
# starlette/routing.py
def compile_path(path: str) -> tuple[Pattern, str, dict]:
    """
    Compiles "/users/{user_id:int}" into:
    - regex: r"^/users/(?P<user_id>[0-9]+)/?$"
    - format: "/users/{user_id}"
    - convertors: {"user_id": IntegerConvertor()}

    Done ONCE at route registration, not per request.
    """
```

### 2. Middleware Stack Lazy Build

```python
# Built on first request, then cached
if self.middleware_stack is None:
    self.middleware_stack = self.build_middleware_stack()
await self.middleware_stack(scope, receive, send)
```

### 3. Dependency Cache Key

```python
# Dependencies with same callable + scopes share result within request
cache_key = (callable, tuple(sorted(oauth_scopes)), computed_scope)
# Stored in dependency_cache dict during solve_dependencies()
```

### 4. Pydantic v2 model_dump_json() — Best for APIs

```python
# model_dump_json() → bytes (Rust serialized, ~5-10x faster than json.dumps)
# model_dump() → dict (Python objects, then json.dumps needed)

# In FastAPI endpoints, return the Pydantic model directly
# FastAPI uses model_dump_json() internally for response_model serialization
@app.get("/users/{id}", response_model=UserRead)
async def get_user(id: UUID) -> UserInDB:
    return user_db_object  # FastAPI serializes with Pydantic Rust engine
```

### 5. Run Sync Functions in Thread Pool

```python
# FastAPI/Starlette use anyio.to_thread.run_sync() for sync functions
# This is the same as asyncio.to_thread() but compatible with all backends

# For sync dependencies and sync path operations:
@app.get("/sync-endpoint")
def sync_endpoint():  # Regular def, not async
    # Runs in thread pool automatically (Starlette/FastAPI does this)
    return expensive_sync_operation()

# For explicit thread pool execution:
from anyio import to_thread
result = await to_thread.run_sync(blocking_function)
```

### 6. response_model_exclude_unset + response_model_exclude_none

```python
# Reduce payload size by excluding empty/unset fields
@app.get("/items/{id}", response_model=ItemRead,
         response_model_exclude_unset=True,
         response_model_exclude_none=True)
async def get_item(id: UUID): ...

# Performance: smaller JSON = faster serialization + less network
```

---

## Key File Map {#key-file-map}

| What | File | Key Contents |
|------|------|-------------|
| FastAPI class | `fastapi/applications.py` | FastAPI(Starlette), all __init__ params |
| Path operations | `fastapi/routing.py` | APIRoute, request_response(), AsyncExitStack |
| DI system | `fastapi/dependencies/utils.py` | get_dependant(), solve_dependencies() |
| DI models | `fastapi/dependencies/models.py` | Dependant dataclass, cache_key |
| Parameters | `fastapi/params.py` | Query, Path, Header, Cookie, Body, Form, File, Depends, Security |
| Security | `fastapi/security/__init__.py` | All security schemes |
| Responses | `fastapi/responses.py` | All response types |
| JSON encoding | `fastapi/encoders.py` | ENCODERS_BY_TYPE fallback map |
| Starlette app | `starlette/applications.py` | Starlette class, middleware build |
| Route matching | `starlette/routing.py` | compile_path(), Route.matches() |
| Background tasks | `starlette/background.py` | BackgroundTask, BackgroundTasks |
| HTTP responses | `starlette/responses.py` | Response base, StreamingResponse, FileResponse |
| Middleware base | `starlette/middleware/base.py` | BaseHTTPMiddleware |
| Pydantic model | `pydantic/main.py` | BaseModel, model_validate(), model_dump_json() |
| Pydantic fields | `pydantic/fields.py` | FieldInfo, all Field() parameters |
| Validators | `pydantic/functional_validators.py` | field_validator, model_validator, AfterValidator |
| Pydantic config | `pydantic/config.py` | ConfigDict TypedDict with all options |
| Pydantic types | `pydantic/types.py` | Constrained types, EmailStr, SecretStr, etc. |
| Rust engine | `pydantic_core/_pydantic_core.so` | All validation runs here |
| Uvicorn config | `uvicorn/config.py` | Config class, all parameters |
| Uvicorn server | `uvicorn/main.py` | run() function |
| Uvicorn workers | `uvicorn/workers.py` | UvicornWorker (for Gunicorn) |
| AnyIO | `anyio/__init__.py` | create_task_group, to_thread, from_thread |
