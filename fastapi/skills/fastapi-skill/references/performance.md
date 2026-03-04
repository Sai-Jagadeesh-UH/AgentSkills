# Performance Optimization Reference

## Table of Contents
1. [Response Optimization](#response-optimization)
2. [Caching Strategies](#caching)
3. [Database Query Optimization](#db-optimization)
4. [Middleware Ordering](#middleware-ordering)
5. [Load Testing](#load-testing)
6. [Benchmarks & Metrics](#benchmarks)

---

## Response Optimization {#response-optimization}

### Fastest Serialization: Declare Return Types

> **`ORJSONResponse` and `UJSONResponse` are deprecated in modern FastAPI.** Do not use them.

Modern FastAPI serializes through Pydantic's Rust-backed core when you declare a return type or `response_model`. This is equivalent to (or faster than) orjson without extra dependencies.

```python
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class Item(BaseModel):
    name: str
    price: float

# CORRECT — return type triggers Pydantic Rust serialization (fastest path)
@app.get("/items/")
async def list_items() -> list[Item]:
    return items

# Also correct — response_model= when return type differs
@app.get("/items/{id}", response_model=Item)
async def get_item(id: int) -> InternalItem:
    return await fetch_item(id)

# ❌ DEPRECATED — do not use
# from fastapi.responses import ORJSONResponse
# app = FastAPI(default_response_class=ORJSONResponse)
```

If you need the absolute fastest path for large payloads without a Pydantic model:

```python
# model_dump_json() outputs JSON bytes directly — bypasses Python JSON encoder
@app.get("/raw/")
async def raw_response():
    data = Item(name="Widget", price=9.99)
    return Response(content=data.model_dump_json(), media_type="application/json")
```

### Response Model Filtering

```python
# Exclude None and unset fields to reduce payload size
@app.get(
    "/items/{id}",
    response_model=ItemRead,
    response_model_exclude_unset=True,   # skip fields not set
    response_model_exclude_none=True,    # skip None fields
)
async def get_item(id: UUID): ...

# Selective field inclusion (like GraphQL)
@app.get("/items/", response_model=list[ItemRead])
async def list_items(fields: str | None = None):
    if fields:
        include_fields = set(fields.split(","))
        # Use response_model_include dynamically
```

### GZip Compression

```python
from starlette.middleware.gzip import GZipMiddleware

# Compress responses > 1KB
app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=6)
```

### ETag / Conditional Requests

```python
import hashlib
from fastapi import Request
from fastapi.responses import Response

@app.get("/items/{id}")
async def get_item(id: UUID, request: Request):
    item = await item_service.get(id)
    etag = hashlib.md5(item.model_dump_json().encode()).hexdigest()

    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304)  # Not Modified

    return JSONResponse(
        content=item.model_dump(),
        headers={"ETag": etag, "Cache-Control": "max-age=60"},
    )
```

---

## Caching Strategies {#caching}

### fastapi-cache2 (Redis + in-memory)

```bash
pip install fastapi-cache2[redis]
```

```python
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend
from fastapi_cache.decorator import cache
import redis.asyncio as aioredis

@asynccontextmanager
async def lifespan(app: FastAPI):
    r = aioredis.from_url(settings.redis_url, encoding="utf8")
    FastAPICache.init(RedisBackend(r), prefix="fastapi-cache")
    yield

# Cache for 5 minutes
@app.get("/expensive-report")
@cache(expire=300)
async def expensive_report(db: AsyncSession = Depends(get_db)):
    return await report_service.generate_full_report(db)

# Per-user cache key
@app.get("/my-data")
@cache(expire=60, key_builder=lambda func, *args, user=None, **kwargs:
    f"{func.__name__}:{user.id}")
async def my_data(user: CurrentUser):
    return await data_service.get_for_user(user.id)
```

### Manual Redis Cache Pattern

```python
import redis.asyncio as aioredis
import json

async def get_cached_or_fetch(
    redis: aioredis.Redis,
    key: str,
    fetch_func,
    ttl: int = 300,
):
    cached = await redis.get(key)
    if cached:
        return json.loads(cached)

    data = await fetch_func()
    await redis.setex(key, ttl, json.dumps(data, default=str))
    return data

@app.get("/products")
async def list_products(
    category: str | None = None,
    redis: aioredis.Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
):
    cache_key = f"products:{category or 'all'}"
    return await get_cached_or_fetch(
        redis, cache_key,
        lambda: product_service.list(db, category=category),
        ttl=120,
    )
```

### Cache Invalidation

```python
# Pattern: invalidate on mutation
@app.put("/products/{id}")
async def update_product(
    id: UUID,
    data: ProductUpdate,
    redis: aioredis.Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
):
    product = await product_service.update(db, id, data)

    # Invalidate related cache keys
    await redis.delete(f"products:{product.category}")
    await redis.delete("products:all")
    await redis.delete(f"product:{id}")

    return product
```

---

## Database Query Optimization {#db-optimization}

### Eager Loading (N+1 Prevention)

```python
from sqlalchemy.orm import selectinload, joinedload

# selectinload: separate query, best for collections
@app.get("/users/{id}/with-posts")
async def user_with_posts(id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(User)
        .options(selectinload(User.posts).selectinload(Post.tags))
        .where(User.id == id)
    )
    return result.scalar_one_or_none()

# joinedload: single JOIN query, best for single relations
result = await db.execute(
    select(Order)
    .options(joinedload(Order.user))
    .where(Order.id == order_id)
)
```

### Pagination — Cursor vs Offset

```python
# Offset pagination (simple, less efficient for large datasets)
@app.get("/items/")
async def list_items_offset(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    offset = (page - 1) * size
    results = await db.execute(select(Item).offset(offset).limit(size))
    return results.scalars().all()

# Cursor pagination (efficient for large datasets, real-time feeds)
@app.get("/items/cursor")
async def list_items_cursor(
    cursor: UUID | None = None,   # ID of last seen item
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    query = select(Item).order_by(Item.created_at.desc()).limit(size)
    if cursor:
        # Get the cursor item's timestamp
        cursor_item = await db.get(Item, cursor)
        query = query.where(Item.created_at < cursor_item.created_at)

    results = await db.execute(query)
    items = results.scalars().all()
    next_cursor = items[-1].id if len(items) == size else None
    return {"items": items, "next_cursor": next_cursor}
```

### Bulk Operations

```python
# Bulk insert (faster than row-by-row)
await db.execute(
    insert(Item),
    [{"name": f"item_{i}", "price": 9.99} for i in range(1000)]
)

# Bulk update
await db.execute(
    update(Item)
    .where(Item.category == "electronics")
    .values(discount=0.1)
)

# Upsert (PostgreSQL)
from sqlalchemy.dialects.postgresql import insert as pg_insert

stmt = pg_insert(Item).values(items_data)
stmt = stmt.on_conflict_do_update(
    index_elements=["sku"],
    set_={"price": stmt.excluded.price, "updated_at": datetime.now(UTC)}
)
await db.execute(stmt)
```

---

## Middleware Ordering {#middleware-ordering}

Order middlewares correctly for best performance. Last added = outermost = runs first:

```python
# CORRECT ORDER (innermost first, outermost last)
app.add_middleware(GZipMiddleware, minimum_size=1000)        # innermost: compresses after all processing
app.add_middleware(CORSMiddleware, allow_origins=["*"])      # CORS before auth
app.add_middleware(TimingMiddleware)                          # timing wraps everything
app.add_middleware(RequestIDMiddleware)                       # request ID wrapping
app.add_middleware(HTTPSRedirectMiddleware)                   # outermost: redirect HTTP→HTTPS first
```

Request flow: HTTPS → RequestID → Timing → CORS → GZip → Route handler

---

## Load Testing {#load-testing}

### locust

```bash
pip install locust
```

```python
# locustfile.py
from locust import HttpUser, task, between

class APIUser(HttpUser):
    wait_time = between(0.1, 1)  # think time between requests
    token: str = ""

    def on_start(self):
        resp = self.client.post("/api/v1/auth/token", data={
            "username": "test@example.com", "password": "testpass"
        })
        self.token = resp.json()["access_token"]

    @task(3)  # weight 3: called 3x more often than weight-1 tasks
    def list_items(self):
        self.client.get(
            "/api/v1/items/",
            headers={"Authorization": f"Bearer {self.token}"},
        )

    @task(1)
    def create_item(self):
        self.client.post(
            "/api/v1/items/",
            json={"name": "Test Item", "price": 9.99},
            headers={"Authorization": f"Bearer {self.token}"},
        )

# Run: locust --host=http://localhost:8000 --users=100 --spawn-rate=10
```

### k6 (JavaScript, CI-friendly)

```javascript
// load_test.js
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '30s', target: 50 },   // ramp up
    { duration: '1m', target: 50 },    // steady state
    { duration: '30s', target: 0 },    // ramp down
  ],
  thresholds: {
    'http_req_duration': ['p(95)<500'],  // 95% under 500ms
    'http_req_failed': ['rate<0.01'],    // <1% error rate
  },
};

export default function() {
  const res = http.get('http://localhost:8000/api/v1/items/');
  check(res, { 'status was 200': (r) => r.status === 200 });
  sleep(0.5);
}
```

---

## Benchmarks & Metrics {#benchmarks}

### Prometheus Metrics

```bash
pip install prometheus-fastapi-instrumentator
```

```python
from prometheus_fastapi_instrumentator import Instrumentator

instrumentator = Instrumentator(
    should_group_status_codes=True,
    should_ignore_untemplated=True,
    should_respect_env_var=True,     # ENABLE_METRICS=true
    should_instrument_requests_inprogress=True,
    excluded_handlers=["/health", "/metrics"],
    inprogress_name="http_requests_inprogress",
)

instrumentator.instrument(app).expose(app, endpoint="/metrics")
```

### Custom Business Metrics

```python
from prometheus_client import Counter, Histogram, Gauge

orders_created = Counter("orders_created_total", "Total orders created", ["status"])
order_value = Histogram("order_value_dollars", "Order value in dollars",
                        buckets=[10, 50, 100, 500, 1000, 5000])
active_users = Gauge("active_users", "Currently active users")

@app.post("/orders/")
async def create_order(data: OrderCreate, user: CurrentUser):
    order = await order_service.create(data)
    orders_created.labels(status="success").inc()
    order_value.observe(order.total_value)
    return order
```

### Performance Targets by Deployment

| Deployment | p50 target | p95 target | p99 target |
|---|---|---|---|
| Single Uvicorn (dev) | <50ms | <200ms | <500ms |
| Gunicorn 4 workers | <30ms | <100ms | <300ms |
| Container App (scaled) | <20ms | <80ms | <200ms |
| Azure Functions (warm) | <50ms | <150ms | <400ms |
| Azure Functions (cold) | <5s | <10s | <15s |
