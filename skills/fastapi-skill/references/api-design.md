# RESTful API Design Reference

## Table of Contents
1. [Resource Naming & URLs](#resource-naming)
2. [HTTP Methods & Status Codes](#http-methods)
3. [Request & Response Patterns](#request-response)
4. [Pagination Schemas](#pagination)
5. [Error Format Standard](#error-format)
6. [API Versioning](#versioning)
7. [OpenAPI Documentation](#openapi-docs)
8. [Common Design Decisions](#design-decisions)

---

## Resource Naming & URLs {#resource-naming}

### Naming Rules

| Rule | Good | Bad |
|---|---|---|
| Plural nouns for collections | `/users` | `/user`, `/getUsers` |
| Lowercase with hyphens | `/order-items` | `/OrderItems`, `/order_items` |
| No verbs in URL | `POST /orders` | `POST /createOrder` |
| Nested for ownership | `/users/{id}/orders` | `/getUserOrders` |
| Max 2 levels of nesting | `/users/{id}/posts` | `/users/{id}/posts/{pid}/comments/{cid}` |

### URL Patterns

```
# Collections
GET    /api/v1/users           → list users (paginated)
POST   /api/v1/users           → create user

# Single resource
GET    /api/v1/users/{id}      → get user
PUT    /api/v1/users/{id}      → full replace
PATCH  /api/v1/users/{id}      → partial update
DELETE /api/v1/users/{id}      → delete user

# Sub-resources (ownership relationship)
GET    /api/v1/users/{id}/orders       → list user's orders
POST   /api/v1/users/{id}/orders       → create order for user
GET    /api/v1/orders/{id}             → get order (direct access)

# Actions (when REST verbs don't fit)
POST   /api/v1/users/{id}/activate     → action: activate user
POST   /api/v1/orders/{id}/cancel      → action: cancel order
POST   /api/v1/auth/token              → action: login
POST   /api/v1/auth/refresh            → action: refresh token
POST   /api/v1/payments/{id}/refund    → action: refund

# Search (complex queries)
GET    /api/v1/users/search?q=john&role=admin    → search
POST   /api/v1/users/search            → complex search (POST body)
```

---

## HTTP Methods & Status Codes {#http-methods}

### Method Semantics

| Method | Semantics | Idempotent | Body |
|---|---|---|---|
| GET | Retrieve | Yes | No |
| POST | Create | No | Yes |
| PUT | Full replace | Yes | Yes |
| PATCH | Partial update | No | Yes |
| DELETE | Delete | Yes | No |
| HEAD | Check existence | Yes | No |
| OPTIONS | CORS preflight | Yes | No |

### Status Code Guide

```python
# FastAPI endpoint examples with correct status codes

# 200 OK — GET, PUT, PATCH success
@app.get("/users/{id}", response_model=UserRead)
async def get_user(id: UUID): ...

# 201 Created — POST success, include Location header
@app.post("/users/", response_model=UserRead, status_code=201)
async def create_user(data: UserCreate, response: Response):
    user = await user_service.create(data)
    response.headers["Location"] = f"/api/v1/users/{user.id}"
    return user

# 204 No Content — DELETE, or action with no response body
@app.delete("/users/{id}", status_code=204)
async def delete_user(id: UUID): ...

# 400 Bad Request — malformed request, business logic error
raise HTTPException(status_code=400, detail="Cannot delete user with active orders")

# 401 Unauthorized — not authenticated
raise HTTPException(
    status_code=401,
    detail="Authentication required",
    headers={"WWW-Authenticate": "Bearer"},
)

# 403 Forbidden — authenticated but insufficient permissions
raise HTTPException(status_code=403, detail="Admin role required")

# 404 Not Found
raise HTTPException(status_code=404, detail=f"User {id} not found")

# 409 Conflict — duplicate resource, state conflict
raise HTTPException(status_code=409, detail="Email already registered")

# 422 Unprocessable Entity — FastAPI raises automatically for Pydantic errors
# You don't need to raise this manually

# 429 Too Many Requests — rate limiting
raise HTTPException(
    status_code=429,
    detail="Rate limit exceeded",
    headers={"Retry-After": "60"},
)
```

---

## Request & Response Patterns {#request-response}

### Path, Query, and Body Parameters

```python
from typing import Annotated
from fastapi import Query, Path, Body, Header

@app.get("/users/{user_id}/orders")
async def list_user_orders(
    # Path parameter — always required
    user_id: Annotated[UUID, Path(description="User identifier")],

    # Query parameters — optional with defaults
    status: Annotated[str | None, Query(description="Filter by status")] = None,
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    size: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 20,
    sort: Annotated[str, Query(description="Sort field")] = "-created_at",

    # Header — for custom headers
    x_correlation_id: Annotated[str | None, Header()] = None,

    # Current user (from auth dependency)
    current_user: CurrentUser = None,
): ...
```

### PATCH vs PUT

```python
# PUT — full replace (all fields required)
class UserPut(BaseModel):
    email: EmailStr          # required
    full_name: str           # required
    is_active: bool          # required

# PATCH — partial update (all fields optional)
class UserPatch(BaseModel):
    email: EmailStr | None = None
    full_name: str | None = None
    is_active: bool | None = None

@app.patch("/users/{id}", response_model=UserRead)
async def patch_user(
    id: UUID,
    data: UserPatch,
    db: AsyncSession = Depends(get_db),
):
    # Only update fields that were provided
    update_data = data.model_dump(exclude_unset=True)
    await db.execute(update(User).where(User.id == id).values(**update_data))
    return await db.get(User, id)
```

### Bulk Operations

```python
# Bulk create
@app.post("/users/bulk", response_model=list[UserRead], status_code=201)
async def bulk_create_users(users: Annotated[list[UserCreate], Body(max_length=100)]):
    return await user_service.bulk_create(users)

# Bulk delete
class BulkDeleteRequest(BaseModel):
    ids: Annotated[list[UUID], Field(min_length=1, max_length=100)]

@app.delete("/users/bulk", status_code=204)
async def bulk_delete_users(data: BulkDeleteRequest):
    await user_service.bulk_delete(data.ids)
```

---

## Pagination Schemas {#pagination}

### Offset Pagination Schema

```python
# schemas/pagination.py
from typing import Generic, TypeVar
from pydantic import BaseModel, Field
from math import ceil

T = TypeVar("T")

class PageParams(BaseModel):
    """Query parameters for pagination — use as dependency"""
    page: int = Field(1, ge=1, description="Page number (1-based)")
    size: int = Field(20, ge=1, le=100, description="Items per page")

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.size

class Page(BaseModel, Generic[T]):
    """Standard paginated response"""
    items: list[T]
    total: int = Field(description="Total number of items across all pages")
    page: int = Field(description="Current page number")
    size: int = Field(description="Items per page")
    pages: int = Field(description="Total number of pages")
    has_next: bool
    has_prev: bool

    @classmethod
    def create(cls, items: list[T], total: int, params: PageParams) -> "Page[T]":
        pages = ceil(total / params.size) if total > 0 else 0
        return cls(
            items=items,
            total=total,
            page=params.page,
            size=params.size,
            pages=pages,
            has_next=params.page < pages,
            has_prev=params.page > 1,
        )

# Usage
@app.get("/users/", response_model=Page[UserRead])
async def list_users(
    params: PageParams = Depends(),
    db: AsyncSession = Depends(get_db),
):
    users, total = await user_repo.list_paginated(
        offset=params.offset, limit=params.size
    )
    return Page.create(users, total, params)
```

### Cursor Pagination Schema

```python
class CursorPage(BaseModel, Generic[T]):
    items: list[T]
    next_cursor: str | None = Field(None, description="Use as 'cursor' in next request")
    has_more: bool

@app.get("/feed/", response_model=CursorPage[PostRead])
async def get_feed(
    cursor: str | None = Query(None, description="Cursor from previous response"),
    size: int = Query(20, ge=1, le=50),
):
    posts, next_cursor = await feed_service.get_page(cursor, size)
    return CursorPage(
        items=posts,
        next_cursor=next_cursor,
        has_more=next_cursor is not None,
    )
```

---

## Error Format Standard {#error-format}

### Consistent Error Response

```python
# schemas/errors.py
from pydantic import BaseModel

class ErrorDetail(BaseModel):
    field: str | None = None   # field name for validation errors
    message: str
    code: str | None = None    # machine-readable error code

class ErrorResponse(BaseModel):
    error: str              # human-readable summary
    details: list[ErrorDetail] = []
    request_id: str | None = None

# Custom exception handler
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error=exc.detail,
            request_id=getattr(request.state, "request_id", None),
        ).model_dump(),
    )

# Pydantic validation error handler
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    details = []
    for error in exc.errors():
        field = ".".join(str(loc) for loc in error["loc"] if loc != "body")
        details.append(ErrorDetail(field=field, message=error["msg"], code=error["type"]))

    return JSONResponse(
        status_code=422,
        content=ErrorResponse(
            error="Validation failed",
            details=details,
            request_id=getattr(request.state, "request_id", None),
        ).model_dump(),
    )
```

---

## API Versioning {#versioning}

### URL Path Versioning (recommended)

```python
# app/api/router.py
from fastapi import APIRouter

v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(users_router, prefix="/users", tags=["Users"])
v1_router.include_router(items_router, prefix="/items", tags=["Items"])

# Mount v1
app.include_router(v1_router)

# When v2 is needed
v2_router = APIRouter(prefix="/api/v2")
# Mount v2 alongside v1 (both work simultaneously)
app.include_router(v2_router)
```

### Deprecation Pattern

```python
@app.get("/api/v1/users/", deprecated=True, include_in_schema=True)
async def list_users_v1():
    """
    **Deprecated**: Use `/api/v2/users/` instead.
    Will be removed in API version 3.0.
    """
    ...
```

---

## OpenAPI Documentation {#openapi-docs}

### Rich API Documentation

```python
app = FastAPI(
    title="My API",
    version="1.0.0",
    description="""
## My API

A complete REST API for managing resources.

### Authentication

Use Bearer token authentication. Get a token from `/api/v1/auth/token`.

### Rate Limiting

- 100 requests/minute per IP for unauthenticated endpoints
- 1000 requests/minute per user for authenticated endpoints
""",
    contact={"name": "API Team", "email": "api@example.com"},
    license_info={"name": "MIT"},
    openapi_tags=[
        {"name": "Users", "description": "User management operations"},
        {"name": "Items", "description": "Item CRUD operations"},
        {"name": "Auth", "description": "Authentication and token management"},
    ],
    servers=[
        {"url": "https://api.example.com", "description": "Production"},
        {"url": "https://staging-api.example.com", "description": "Staging"},
        {"url": "http://localhost:8000", "description": "Local development"},
    ],
)

# Endpoint documentation
@app.post(
    "/users/",
    response_model=UserRead,
    status_code=201,
    summary="Create a new user",
    description="Create a new user account. Returns the created user without the password.",
    response_description="The created user object",
    responses={
        409: {"description": "Email already registered"},
        422: {"description": "Validation error"},
    },
)
async def create_user(
    data: Annotated[UserCreate, Body(
        example={
            "email": "user@example.com",
            "password": "SecurePass123!",
            "full_name": "John Doe",
        }
    )]
): ...
```

---

## Common Design Decisions {#design-decisions}

### Should I nest resources?

```
# YES — when the child cannot exist without the parent
POST /users/{id}/addresses    ← address belongs to user
GET  /orders/{id}/items       ← order items are part of order

# NO — when the child has independent existence or multiple parents
GET  /products                ← not /categories/{id}/products (products are independent)
GET  /tags                    ← not nested, tags are global
```

### Soft Delete vs Hard Delete

```python
# Soft delete (recommended for most domains)
@app.delete("/users/{id}", status_code=204)
async def delete_user(id: UUID, db: AsyncSession = Depends(get_db)):
    await db.execute(
        update(User).where(User.id == id)
        .values(deleted_at=datetime.now(UTC), is_active=False)
    )

# Restore
@app.post("/users/{id}/restore", response_model=UserRead)
async def restore_user(id: UUID): ...

# Always filter deleted in queries
base_query = select(User).where(User.deleted_at.is_(None))
```

### Return Created Object vs 204

```python
# For creates — return the created object (201 + body)
# Client needs the server-assigned ID, timestamps, etc.
@app.post("/items/", response_model=ItemRead, status_code=201)

# For updates — return the updated object (200 + body) OR 204
# Prefer 200 + body so client has the latest state
@app.put("/items/{id}", response_model=ItemRead)

# For deletes — 204 No Content (nothing to return)
@app.delete("/items/{id}", status_code=204)
```

### Long-Running Operations

```python
# Pattern: return 202 Accepted with a job ID
@app.post("/reports/generate", status_code=202)
async def generate_report(
    params: ReportParams,
    queue = Depends(get_task_queue),
):
    job_id = await queue.enqueue_job("generate_report", params.model_dump())
    return {"job_id": job_id, "status_url": f"/api/v1/jobs/{job_id}"}

@app.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    job = await job_service.get(job_id)
    return {
        "id": job_id,
        "status": job.status,  # pending | running | completed | failed
        "result_url": f"/api/v1/reports/{job.result_id}" if job.status == "completed" else None,
        "error": job.error if job.status == "failed" else None,
    }
```
