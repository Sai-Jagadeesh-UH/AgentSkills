# Rate Limiting & Constraint Negotiation Reference

## Table of Contents
1. [Why Rate Limiting is Non-Negotiable](#why)
2. [Algorithm Comparison](#algorithms)
3. [Granularity Tiers](#granularity)
4. [slowapi Implementation](#slowapi)
5. [Redis Distributed Rate Limiting](#redis-rate-limit)
6. [Payload & Body Constraints](#payload-limits)
7. [Idempotency & Retry Contracts](#idempotency)
8. [Pydantic Model Negotiation Checklist](#model-negotiation)
9. [Constraint Negotiation Playbook](#playbook)

---

## Why Rate Limiting is Non-Negotiable {#why}

| Risk | Consequence Without Rate Limiting |
|------|----------------------------------|
| Client bug (infinite loop) | Serverless bill: $10K+ overnight |
| Single tenant overuse | Degrades all other tenants (SLA breach) |
| Credential stuffing / brute force | Auth bypass risk |
| Scraping | Database overload, data theft |
| DoS amplification | 500 errors, cascading failures |
| Runaway background retry | Same as client bug |

**Rate limiting is insurance, not an obstacle.**

---

## Algorithm Comparison {#algorithms}

| Algorithm | Allows Burst | Accuracy | Redis Keys | Recommended For |
|-----------|-------------|----------|------------|-----------------|
| **Fixed Window** | Yes (thundering herd at window edge) | Low | 1 counter | Internal tools, simple cases |
| **Sliding Window Log** | Smooth | Exact | 1 ZSET | External APIs, billing-accurate |
| **Token Bucket** | Yes (controlled burst) | High | 2 keys | Client-facing APIs with bursting |
| **Leaky Bucket** | No | Perfect | 1 key | Upstream API protection, smoothing |

### Thundering Herd Explained

Fixed window allows a client to use their full quota at the end of one window and again at the start of the next — effectively 2× the rate limit in a short burst. Sliding window prevents this.

---

## Granularity Tiers {#granularity}

Design rate limits at multiple levels simultaneously:

```python
# Tier 1: Per-IP (protect unauthenticated endpoints)
# Tier 2: Per-User (authenticated rate limiting)
# Tier 3: Per-API-Key (machine-to-machine)
# Tier 4: Per-Endpoint (expensive operations get stricter limits)
# Tier 5: Per-Tier (subscription-based: Free / Pro / Enterprise)

# Example limits by tier
RATE_LIMITS = {
    "free":       {"default": "100/day",   "export": "5/day",    "search": "20/hour"},
    "pro":        {"default": "10000/day", "export": "100/day",  "search": "500/hour"},
    "enterprise": {"default": "unlimited", "export": "1000/day", "search": "unlimited"},
}
```

---

## slowapi Implementation {#slowapi}

```bash
pip install slowapi
```

### Basic Setup

```python
# app/main.py
from fastapi import FastAPI, Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)

app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
```

### Per-Endpoint Limits

```python
from slowapi.util import get_remote_address

@app.get("/search")
@limiter.limit("20/minute")
async def search(request: Request, q: str) -> list[ItemRead]:
    """Search endpoint — limited to 20/minute per IP."""
    return await item_service.search(q)

@app.post("/export")
@limiter.limit("5/day")
async def export_data(request: Request) -> StreamingResponse:
    """Expensive export — limited to 5/day per IP."""
    return StreamingResponse(generate_export(), media_type="text/csv")
```

### User-Aware Rate Limiting (Per-User)

```python
def get_user_id_or_ip(request: Request) -> str:
    """Use authenticated user ID if available, else fall back to IP."""
    user = getattr(request.state, "user", None)
    if user:
        return f"user:{user.id}"
    return get_remote_address(request)

user_limiter = Limiter(key_func=get_user_id_or_ip)

@app.get("/api/data")
@user_limiter.limit("1000/hour")
async def get_data(request: Request, current_user: User = Depends(get_current_user)):
    ...
```

### Subscription-Tier Rate Limiting

```python
from functools import wraps

def tier_limit(free: str, pro: str, enterprise: str = "10000/minute"):
    """Apply different rate limits based on user subscription tier."""
    def decorator(func):
        @wraps(func)
        async def wrapper(request: Request, current_user: User = Depends(get_current_user), **kwargs):
            limits = {"free": free, "pro": pro, "enterprise": enterprise}
            limit = limits.get(current_user.tier, free)
            # Dynamic limit injection
            request.state.view_rate_limit = limit
            return await func(request=request, current_user=current_user, **kwargs)
        return wrapper
    return decorator

@app.get("/items")
@limiter.limit(lambda request: getattr(request.state, "view_rate_limit", "100/hour"))
@tier_limit(free="100/hour", pro="5000/hour", enterprise="unlimited")
async def list_items(request: Request, current_user: User = Depends(get_current_user)):
    ...
```

### Custom 429 Response

```python
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={
            "error": "rate_limit_exceeded",
            "message": f"Rate limit exceeded: {exc.detail}",
            "retry_after": exc.retry_after,  # seconds to wait
        },
        headers={
            "Retry-After": str(exc.retry_after),
            "X-RateLimit-Limit": str(exc.limit),
        }
    )

app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
```

---

## Redis Distributed Rate Limiting {#redis-rate-limit}

slowapi uses in-memory storage by default — **does not work across multiple instances**. For multi-instance deployments, use Redis.

### slowapi with Redis Backend

```python
from slowapi import Limiter
from slowapi.util import get_remote_address
import redis.asyncio as aioredis

redis_client = aioredis.from_url("redis://localhost:6379", encoding="utf-8")

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="redis://localhost:6379",  # Redis backend
)
```

### Custom Sliding Window (Lua Script — Atomic)

For precise sliding window without thundering herd, use a Redis Lua script:

```python
import time
import redis.asyncio as aioredis

SLIDING_WINDOW_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])

-- Remove entries outside the window
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)

-- Count current entries
local count = redis.call('ZCARD', key)

if count < limit then
    -- Add current request with timestamp as score
    redis.call('ZADD', key, now, now .. math.random())
    redis.call('EXPIRE', key, window / 1000 + 1)
    return {1, limit - count - 1}  -- {allowed, remaining}
else
    return {0, 0}  -- {blocked, 0}
end
"""

class SlidingWindowRateLimiter:
    def __init__(self, redis: aioredis.Redis):
        self.redis = redis
        self._script = self.redis.register_script(SLIDING_WINDOW_SCRIPT)

    async def is_allowed(
        self,
        key: str,
        limit: int,
        window_ms: int = 60_000,  # 1 minute default
    ) -> tuple[bool, int]:
        """Returns (allowed, remaining). Atomic via Lua."""
        now_ms = int(time.time() * 1000)
        result = await self._script(
            keys=[f"rl:{key}"],
            args=[now_ms, window_ms, limit],
        )
        return bool(result[0]), int(result[1])


# FastAPI dependency
async def check_rate_limit(
    request: Request,
    limiter: SlidingWindowRateLimiter = Depends(get_rate_limiter),
    current_user: User = Depends(get_current_user),
):
    key = f"user:{current_user.id}:api"
    limit = {"free": 100, "pro": 5000, "enterprise": 100000}[current_user.tier]

    allowed, remaining = await limiter.is_allowed(key, limit, window_ms=3_600_000)  # 1h

    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
                "Retry-After": "3600",
            }
        )

    # Inject headers into response via middleware or response object
    request.state.rate_limit_remaining = remaining
```

### Standard Rate Limit Headers

Always return these headers on every response (not just 429):

```python
# Middleware to inject rate limit headers
@app.middleware("http")
async def add_rate_limit_headers(request: Request, call_next):
    response = await call_next(request)
    remaining = getattr(request.state, "rate_limit_remaining", None)
    if remaining is not None:
        response.headers["X-RateLimit-Remaining"] = str(remaining)
    return response
```

```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 847
X-RateLimit-Reset: 1704067200    # Unix timestamp when window resets
Retry-After: 60                  # On 429: seconds to wait
```

---

## Payload & Body Constraints {#payload-limits}

### Request Body Size Limits

```python
# Reject oversized bodies at the ASGI level (before Pydantic validation)
from starlette.middleware.base import BaseHTTPMiddleware

class MaxBodySizeMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_bytes: int = 1_048_576):  # 1MB default
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.max_bytes:
            return JSONResponse(
                status_code=413,
                content={"error": "request_too_large", "max_bytes": self.max_bytes}
            )
        return await call_next(request)

app.add_middleware(MaxBodySizeMiddleware, max_bytes=5_242_880)  # 5MB for file uploads

# Per-endpoint: use UploadFile with size validation
@app.post("/upload")
async def upload_file(file: UploadFile) -> dict:
    MAX_SIZE = 10 * 1024 * 1024  # 10MB
    content = await file.read(MAX_SIZE + 1)
    if len(content) > MAX_SIZE:
        raise HTTPException(413, f"File exceeds {MAX_SIZE // 1024 // 1024}MB limit")
    ...
```

### Query Parameter Validation

```python
from fastapi import Query
from typing import Annotated

# Paginated list endpoint constraints
@app.get("/items")
async def list_items(
    page: Annotated[int, Query(ge=1, le=10000, description="Page number")] = 1,
    size: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 20,
    q: Annotated[str | None, Query(max_length=200, description="Search query")] = None,
    sort: Annotated[str, Query(pattern="^(created_at|name|price):(asc|desc)$")] = "created_at:desc",
) -> Page[ItemRead]:
    ...
```

---

## Idempotency & Retry Contracts {#idempotency}

### Why Idempotency Keys Matter

Clients retry on timeout. Without idempotency, a timed-out POST creates duplicate records.

```
Rule: Any state-changing operation that clients might retry MUST be idempotent.
- POST (create) → idempotency key required
- PUT/PATCH → idempotent by design (same data = same result)
- DELETE → idempotent by design (deleting deleted = no-op)
```

### Idempotency Key Middleware

```python
from fastapi import Header, Depends
import hashlib
import json

class IdempotencyMiddleware:
    """Cache POST results by Idempotency-Key header. TTL: 24 hours."""

    async def __call__(
        self,
        request: Request,
        call_next,
        redis: aioredis.Redis,
    ):
        if request.method != "POST":
            return await call_next(request)

        key = request.headers.get("Idempotency-Key")
        if not key:
            return await call_next(request)

        # Check for cached result
        cache_key = f"idem:{hashlib.sha256(key.encode()).hexdigest()}"
        cached = await redis.get(cache_key)
        if cached:
            data = json.loads(cached)
            return JSONResponse(
                content=data["body"],
                status_code=data["status_code"],
                headers={"X-Idempotent-Replayed": "true"},
            )

        response = await call_next(request)

        # Cache successful responses (2xx)
        if 200 <= response.status_code < 300:
            body = b""
            async for chunk in response.body_iterator:
                body += chunk
            await redis.setex(cache_key, 86400, json.dumps({
                "body": json.loads(body),
                "status_code": response.status_code,
            }))
            return Response(content=body, status_code=response.status_code,
                          headers=dict(response.headers), media_type=response.media_type)

        return response
```

---

## Pydantic Model Negotiation Checklist {#model-negotiation}

Use this checklist when reviewing or designing Pydantic models. Challenge each field decision.

### Field Type Decisions

| Decision | Strict Choice | Flexible Choice | When to Negotiate |
|----------|--------------|-----------------|-------------------|
| **ID type** | `UUID` | `int` | UUID for public APIs (no enumeration), int for internal/joins |
| **String enum** | `str(Enum)` | `str` | Enum if values are known/limited; free string if extensible |
| **Timestamp** | `datetime` (TZ-aware) | `int` (epoch) | Always use datetime + UTC; epoch only for interop |
| **Boolean** | `bool` | `int` (0/1) | Always bool in Pydantic; int only at DB column level |
| **Decimal money** | `Decimal` | `float` | Always `Decimal` for money — floats cause rounding errors |
| **Nested model** | Flat fields | `NestedModel` | Flat = simpler, faster; nested = cleaner for complex types |

### Field Constraint Negotiation

```python
# For each string field, ask:
# 1. What's the max realistic length? (default to something reasonable)
# 2. What characters are valid? (alphanumeric? unicode? HTML?)
# 3. Is empty string valid or should it be None?

class ProductCreate(BaseModel):
    # NEGOTIATED: max_length prevents 10MB text field attacks
    name: Annotated[str, Field(min_length=1, max_length=200, strip_whitespace=True)]

    # NEGOTIATED: slug prevents XSS/injection in URL-embedded strings
    slug: Annotated[str, Field(min_length=1, max_length=100, pattern=r'^[a-z0-9-]+$')]

    # NEGOTIATED: Decimal for money (not float)
    price: Annotated[Decimal, Field(gt=0, le=Decimal("999999.99"), decimal_places=2)]

    # NEGOTIATED: bounded list prevents 10,000-tag payloads
    tags: Annotated[list[str], Field(max_length=10, default_factory=list)]

    # NEGOTIATED: strict enum prevents typos in category
    category: ProductCategory  # str(Enum), not free string

    # NEGOTIATED: optional description with max length
    description: Annotated[str | None, Field(max_length=5000, default=None)]
```

### Validation Mode Selection

```python
from pydantic import BaseModel, ConfigDict

class FinancialTransaction(BaseModel):
    """Strict mode for financial data — reject type coercion."""
    model_config = ConfigDict(strict=True)  # "123" will NOT coerce to int 123

    amount: Decimal
    currency: CurrencyCode  # must be exact enum value
    reference_id: UUID       # must be UUID, not a string


class InternalToolModel(BaseModel):
    """Lax mode for internal tools — accept coercion."""
    # default: strict=False
    count: int  # "5" → 5 (accepted)
    active: bool  # "true" → True (accepted)
```

### Schema Evolution Rules (Backwards Compatibility)

| Change | Breaking? | Strategy |
|--------|-----------|----------|
| Add optional field | No | Safe to add |
| Add required field | Yes | Must be optional with default, then promote |
| Remove field | Yes | Deprecate with `deprecated=True` in Field(), remove in next major version |
| Change field type | Yes | Add new field, deprecate old, remove in v2 |
| Rename field | Yes | Use `AliasChoices` to accept both names during migration |
| Tighten validation (add constraint) | Yes | Communicate to clients, give 30-day notice |
| Loosen validation | No | Safe (clients already passing the stricter data) |

```python
# Deprecation pattern — accept old and new names
from pydantic import Field, AliasChoices

class UserRead(BaseModel):
    # Accept both 'full_name' (old) and 'display_name' (new)
    display_name: str = Field(
        validation_alias=AliasChoices('display_name', 'full_name')
    )
    # Add to changelog and sunset full_name in 60 days
```

---

## Constraint Negotiation Playbook {#playbook}

### How to Challenge User Assumptions

As a senior engineer, push back on these common naive patterns:

**"No rate limiting needed, it's internal"**
> Response: Internal APIs get abused by bugs, not people. One misconfigured cron job can flood an internal API with 10M requests. Add per-service limits at minimum.

**"We'll add rate limiting later"**
> Response: Retrofitting rate limiting requires changing response contracts (adding headers), updating clients, and redeploying. Cost is 3× now vs 10× later. Do it in Phase 1.

**"Set the rate limit high so no one hits it"**
> Response: Start at 2× your measured P95 legitimate traffic. Review monthly. Limits that are never hit provide no protection.

**"All fields are required, no defaults"**
> Response: Required fields are a breaking change contract. Every field added later must be optional. Start with minimum required fields; add optional ones freely.

**"Store full text/JSON blob as a single field"**
> Response: What's the max size? Who validates it? How do you query into it? Can a client send 100MB? Add `max_length` or use a proper schema.

**"We'll figure out SLA when we launch"**
> Response: SLA determines minimum replicas, DB tier, and monitoring alerting thresholds. Launching without an SLA means you don't know if you're meeting it.

### Constraint Setting Process

```
1. Measure → 2. Set → 3. Observe → 4. Tighten

1. MEASURE: Run load test at expected peak. Record P95 latency, RPS, error rate.
2. SET: Rate limit = 2× measured P95 legitimate RPS per client.
       Payload limit = 2× largest realistic legitimate payload.
       Timeout = 3× measured P95 response time.
3. OBSERVE: Monitor 429 rate in production. If 429 rate > 1% of legitimate traffic → limits are too tight.
4. TIGHTEN: After 30 days of baseline data, move toward 1.5× to reduce abuse surface.
```

### SLA Design Template

```markdown
## API SLA for [Service Name] v1

**Availability**: 99.9% monthly (43 min downtime budget)
**Latency**:
  - P50: < 50ms
  - P95: < 200ms
  - P99: < 500ms
**Error Rate**: < 0.1% 5xx over any 5-minute window
**Rate Limits**:
  - Free tier: 100 req/hour per user
  - Pro tier: 5,000 req/hour per user
  - Enterprise: negotiated
**Payload Limits**:
  - Request body: 1MB max
  - Response: no limit (use pagination)
  - File uploads: 50MB max
**Data Retention**: 90 days default, configurable per tenant
**Exclusions**: Scheduled maintenance (2h/month max, 48h notice)
```
