# Cost & Capacity Planning Reference

## Table of Contents
1. [Capacity Math](#capacity-math)
2. [Deployment Cost Comparison](#deployment-costs)
3. [Break-even Analysis](#break-even)
4. [Cost Optimization Patterns](#cost-optimization)
5. [Sizing Quick Reference](#sizing)
6. [Serverless-Specific Patterns](#serverless-patterns)
7. [Cost Monitoring & Alerting](#monitoring)

---

## Capacity Math {#capacity-math}

### Throughput Formula

```
sustained_rps = workers × (1000ms / avg_latency_ms)
```

**Examples:**
| Workers | Avg Latency | Sustained RPS | Notes |
|---------|------------|---------------|-------|
| 4 | 50ms | 80 RPS | Sync workers (blocking I/O) |
| 4 | 50ms | 4,000+ RPS | Async workers (non-blocking I/O) |
| 9 | 20ms | 450 RPS | Gunicorn 4-core sync |
| 9 | 20ms | 45,000+ RPS | Gunicorn 4-core async (asyncio) |

> **Key insight**: Async workers don't block during I/O waits. 1 async worker can handle thousands of concurrent DB queries simultaneously. Always use `async def` + async DB driver.

### Peak Headroom Rules

- **Design for**: 3× average traffic
- **Survive**: 10× spikes (via circuit breaker + queue shedding)
- **Auto-scale trigger**: ≥ 70% CPU or ≥ 10 concurrent requests per instance
- **Scale-down lag**: keep at least 2 minimum instances in prod (no cold starts for users)

### Memory Per Process

| Worker Type | Memory/Worker | Notes |
|-------------|--------------|-------|
| Uvicorn async | 40–80 MB | Recommended for FastAPI |
| Gunicorn sync | 80–120 MB | Higher due to thread overhead |
| With ML model loaded | 500 MB–4 GB | Pin to dedicated nodes |

### DB Connection Pool Sizing

```python
# Formula
pool_size = workers × connections_per_worker

# Async (asyncpg/asyncmy) — fewer connections needed
# Each coroutine waits without holding a connection
pool_size = workers × 5   # 5 connections/worker is typical

# Sync (psycopg2) — 1 connection per thread
pool_size = workers × threads_per_worker

# Example: 4 Gunicorn async workers
pool_size = 4 × 5 = 20 connections  # plenty for 4,000+ RPS
```

**⚠️ Managed PostgreSQL limits:**
- Azure Database for PostgreSQL Flexible: 50–5,000 max connections by tier
- Serverless (Functions): each cold start opens new connections → use PgBouncer or built-in pooling

### Latency Targets → Worker Count

```python
def workers_needed(target_rps: int, avg_latency_ms: int, headroom: float = 3.0) -> int:
    """Returns minimum workers for target RPS at given latency with headroom."""
    rps_per_worker = 1000 / avg_latency_ms  # sync estimate
    return math.ceil((target_rps * headroom) / rps_per_worker)

# Example: 500 RPS target, 30ms avg latency, async (divide by 100 for async multiplier)
# Sync:  math.ceil((500 × 3) / (1000/30)) = math.ceil(1500/33) = 46 workers (impractical)
# Async: 4 workers easily handles 500 RPS at 30ms (1000/30 × 4 = 133 RPS/worker × ~30× async boost)
```

---

## Deployment Cost Comparison {#deployment-costs}

### Monthly Cost at 30M Requests (~350 RPS sustained)

| Platform | Cold Starts | ~Monthly Cost (USD) | Best For | Complexity |
|----------|------------|---------------------|----------|------------|
| **Azure Functions Consumption** | Yes (1-3s) | $6–15 | Spiky / infrequent (<5M req/day) | Low |
| **Azure Functions Flex Consumption** | Minimal (<500ms) | $10–30 | Balanced workloads (2024+ recommended) | Low |
| **Azure Functions Premium (EP1)** | None (always-on) | $150–200 | VNET, consistent, compliance | Medium |
| **Azure Container Apps (Consumption)** | Yes (min=0) | $15–50 | HTTP workloads, event-driven | Low |
| **Azure Container Apps (Dedicated D2)** | None | $80–180 | Predictable load, min replicas | Medium |
| **Azure AKS (2× D2s_v3)** | None | $200–500+ | Microservices, multi-tenant, full control | High |
| **AWS Lambda** | Yes (~1s) | $4–10 | AWS ecosystem, simple functions | Low |
| **GCP Cloud Run** | Minimal | $8–25 | GCP ecosystem, generous free tier | Low |
| **Docker on VM (D2s_v3 Linux)** | None | $70–100 (fixed) | Sustained high traffic, cost predictable | Medium |
| **Docker on VM (B2s Spot)** | None | $15–25 (fixed) | Dev/staging, non-critical | Medium |

> **Prices are approximate for East US / West Europe regions. Check Azure/AWS pricing calculator for exact figures.**

### Cost Breakdown Components

**Azure Functions Consumption:**
```
Cost = (executions × $0.20/million) + (GB-seconds × $0.000016)
# 30M executions = $6 + compute time
# 512MB × 200ms average = 0.1 GB-s/req × 30M = 3M GB-s = $48 → total ~$54/month at scale
# Optimize: reduce memory allocation, reduce avg execution time
```

**Azure Container Apps (Consumption):**
```
Cost = (vCPU-seconds × $0.000024) + (GiB-seconds × $0.000003) + requests
# 0.25 vCPU × 200ms × 30M req = 1.5M vCPU-seconds = $36 + memory
# Scale to zero saves ~$30/month vs always-on
```

**Docker on VM:**
```
Cost = VM hourly × 730 hours = fixed regardless of traffic
D2s_v3 (2vCPU, 8GiB): ~$96/month on-demand, ~$45/month 1yr reserved
B2s (2vCPU, 4GiB):    ~$40/month on-demand, ~$20/month 1yr reserved
```

---

## Break-even Analysis {#break-even}

### Serverless → Container Apps

```
Break-even occurs when:
  serverless_cost(req/month) > container_cost(fixed/month)

Approximate crossover: ~5–10M requests/day (150–300M/month)
At 200M req/month:
  - Azure Functions: ~$40–80/month (after free tier)
  - Container Apps Dedicated: ~$150/month
  - VM (D2s_v3): ~$96/month ← wins at this scale

Decision: If traffic is predictable and >5M req/day → prefer VM or Container Apps Dedicated.
```

### Container Apps → AKS

Move to AKS when you need:
- 50+ replicas (AKS node pooling is more efficient)
- Multi-tenant isolation (namespace per tenant)
- Complex networking (service mesh, Dapr, VNET peering)
- Custom autoscaling (KEDA triggers beyond HTTP)
- Multi-region active-active

**AKS overhead cost**: ~$200/month minimum (control plane + 2× D2s_v3 node minimum).

### VM Reserved Instances

| Commitment | Savings vs On-Demand |
|-----------|---------------------|
| 1-year reserved | ~40% |
| 3-year reserved | ~60% |
| Spot instances | ~80% (interruption risk) |

> **Rule**: For workloads running >8 hours/day consistently → buy reserved. For dev/test → spot or B-series.

---

## Cost Optimization Patterns {#cost-optimization}

### 1. PgBouncer for Serverless DB Connections

Managed PostgreSQL charges by tier, and tiers have max connection limits. Serverless functions open a new connection per cold start — exhaust limits fast.

```bash
# Options:
# 1. Azure Database Flexible Server built-in PgBouncer (recommended)
#    Enable via portal: Server parameters → pgbouncer.enabled = ON
# 2. Self-hosted PgBouncer sidecar container
# 3. Neon DB / Supabase (built-in serverless-friendly pooling)

# In SQLAlchemy — short pool for serverless
engine = create_async_engine(
    DATABASE_URL,
    pool_size=2,          # low — serverless scales out, not up
    max_overflow=3,
    pool_timeout=10,
    pool_recycle=300,     # recycle before Azure's 600s idle timeout
    pool_pre_ping=True,   # detect dead connections
)
```

### 2. Redis Cache ROI

```python
# Cost analysis:
# DB query (managed PG, D2 tier):    ~$0.000005 per query in compute
# Redis hit (Azure Cache for Redis C1): ~$0.000001 per operation
# Cache saves: 5× per hit

# At 30M requests/day with 80% cache hit rate:
# Without cache: 30M × $0.000005 = $150/day in DB compute
# With cache:    6M DB × $0.000005 + 24M Redis × $0.000001 = $30 + $24 = $54/day
# Savings: ~$96/day = ~$2,880/month
# Redis C1 cost: ~$55/month → ROI: positive from day 1

# Implementation — target cache-hit rate ≥ 80% for GET-heavy APIs
@cache(expire=300)  # 5min TTL for read endpoints
async def get_item(item_id: int) -> ItemRead: ...
```

### 3. Response Compression → Bandwidth Savings

```python
from fastapi.middleware.gzip import GZipMiddleware

app.add_middleware(GZipMiddleware, minimum_size=1000)  # compress responses >1KB

# Savings: 60-80% reduction on JSON payloads
# Azure egress: $0.087/GB (first 10TB)
# 10GB/day uncompressed → 2GB compressed → saves ~$21/month
```

### 4. Structured Logging with Sampling

```python
# Log volume = money (Application Insights, Datadog, etc.)
# Application Insights: ~$2.30/GB ingested

import logging
import random

class SamplingFilter(logging.Filter):
    """Sample INFO logs at 10% in production."""
    RATES = {"DEBUG": 0, "INFO": 0.1, "WARNING": 1.0, "ERROR": 1.0}

    def filter(self, record):
        rate = self.RATES.get(record.levelname, 1.0)
        return rate == 1.0 or random.random() < rate

# 10GB INFO logs/day → 1GB sampled → saves $20.70/day
```

### 5. Scale-to-Zero vs Minimum Replicas

```yaml
# Container Apps — scale rule
scale:
  minReplicas: 0   # scale to zero = no cost when idle ($0)
  maxReplicas: 10
  rules:
    - name: http-scaling
      http:
        metadata:
          concurrentRequests: "10"

# Cost of minimum replica (0.25 vCPU):
# 0.25 vCPU × $0.000024/s × 86400s/day × 30 = ~$15/month per replica
# Cold start penalty: 1-3s for Container Apps
# Decision: if P95 cold start < SLA tolerance → scale-to-zero
#           if SLA < 2s P99 → set minReplicas: 1 (+$15/month)
```

### 6. Right-size Response Payloads

```python
# Payload size directly affects: compute time, bandwidth cost, client parse time

# BAD: return everything
@app.get("/users/{id}")
async def get_user(id: int) -> UserInDB:  # includes hashed_password, internal_notes, etc.

# GOOD: return only what clients need
@app.get("/users/{id}", response_model=UserRead)  # 5 fields vs 20
async def get_user(id: int) -> UserInDB: ...

# GOOD: dynamic field selection
@app.get("/users/{id}")
async def get_user(
    id: int,
    fields: str = Query(None, description="Comma-separated fields: id,email,name")
) -> dict:
    user = await user_repo.get(id)
    if fields:
        allowed = set(fields.split(",")) & UserRead.model_fields.keys()
        return user.model_dump(include=allowed)
    return UserRead.model_validate(user).model_dump()
```

---

## Sizing Quick Reference {#sizing}

### Gunicorn Worker Count

```bash
# Formula: (2 × vCPU) + 1
# But for async (Uvicorn workers), fewer is better:

# 2 vCPU machine → 5 sync workers OR 2-3 async workers
# 4 vCPU machine → 9 sync workers OR 4-5 async workers
# 8 vCPU machine → 17 sync workers OR 6-8 async workers

# Why fewer async? Each async worker is a single-threaded event loop.
# More workers = more memory + more DB connections.
# With uvloop, 1 async worker can handle 10K+ concurrent I/O operations.

WEB_CONCURRENCY=3  # env var for 4vCPU async deployment
```

### Azure Container Apps Sizing

```yaml
resources:
  cpu: 0.25    # start here for most FastAPI APIs
  memory: 0.5Gi

# Scale triggers
scale:
  rules:
    - http: concurrentRequests: "10"   # scale at 10 concurrent
    - custom: KEDA CPU trigger at 70%

# Upgrade path:
# 0.25 vCPU → 0.5 → 1.0 → 2.0 (test at each tier)
# Measure: p95 latency, error rate, CPU utilization
```

### Azure Functions Sizing

```json
// host.json
{
  "functionTimeout": "00:05:00",
  "extensions": {
    "http": {
      "maxConcurrentRequests": 100,
      "maxOutstandingRequests": 200
    }
  }
}
```

```bash
# Environment variables
FUNCTIONS_WORKER_PROCESS_COUNT=4  # match vCPU count
PYTHON_THREADPOOL_THREAD_COUNT=8  # for sync code in async workers
```

### Database Tier Sizing

| Traffic | DB Tier | Pool Size | Notes |
|---------|---------|-----------|-------|
| < 100 RPS | Azure PG Flexible B1ms | 5-10 | Dev/light prod |
| 100-500 RPS | Azure PG Flexible D2s | 20-50 | Standard prod |
| 500-2000 RPS | Azure PG Flexible D4s | 50-100 | High throughput |
| > 2000 RPS | Azure PG Flexible D8s + read replica | 100-200 | Read replicas for GET |

---

## Serverless-Specific Patterns {#serverless-patterns}

### Cold Start Mitigation

```python
# 1. Lazy imports — defer heavy imports to first request
_settings = None

def get_settings():
    global _settings
    if _settings is None:
        from app.config import Settings
        _settings = Settings()
    return _settings

# 2. Module-level initialization (runs once per worker, not per request)
import httpx
_http_client: httpx.AsyncClient | None = None

async def get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=10.0)
    return _http_client

# 3. Minimize package size (cold start time ∝ package size)
# Use: slim base images, --no-dev dependencies, optional imports
```

### Idempotency Keys (Serverless Critical)

Serverless platforms retry on timeout. Without idempotency, retry = duplicate data.

```python
from fastapi import Header, HTTPException
import redis.asyncio as redis

async def check_idempotency(
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    r: redis.Redis = Depends(get_redis),
) -> str | None:
    if not idempotency_key:
        return None

    result_key = f"idem:{idempotency_key}"
    existing = await r.get(result_key)
    if existing:
        raise HTTPException(200, detail=json.loads(existing))  # return cached result
    return idempotency_key

@app.post("/orders", status_code=201)
async def create_order(
    data: OrderCreate,
    idem_key: str | None = Depends(check_idempotency),
    db: AsyncSession = Depends(get_db),
    r: redis.Redis = Depends(get_redis),
) -> OrderRead:
    order = await order_service.create(db, data)
    result = OrderRead.model_validate(order)

    if idem_key:
        await r.setex(f"idem:{idem_key}", 86400, result.model_dump_json())

    return result
```

### Circuit Breaker Pattern

```python
# Protect downstream dependencies — prevent cascade failures
# pip install circuitbreaker

from circuitbreaker import circuit

@circuit(failure_threshold=5, recovery_timeout=30)
async def call_payment_service(order_id: str) -> dict:
    """Opens circuit after 5 failures; retries after 30s."""
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{PAYMENT_URL}/charge", json={"order_id": order_id})
        response.raise_for_status()
        return response.json()

@app.post("/checkout")
async def checkout(order_id: str):
    try:
        return await call_payment_service(order_id)
    except CircuitBreakerError:
        raise HTTPException(503, "Payment service temporarily unavailable. Please retry.")
```

### Graceful Degradation

```python
# Return partial data rather than failing completely
@app.get("/product/{id}")
async def get_product(id: int, db: AsyncSession = Depends(get_db)) -> ProductRead:
    product = await product_repo.get(id, db)

    # Try to enrich with inventory — degrade gracefully if inventory service is down
    try:
        inventory = await inventory_service.get_stock(id, timeout=0.5)
        product.stock_count = inventory.quantity
    except (httpx.TimeoutException, CircuitBreakerError):
        product.stock_count = None  # degrade: return product without stock info

    return product
```

---

## Cost Monitoring & Alerting {#monitoring}

### Azure Cost Alerts

```bash
# Create budget alert at 80% of monthly budget
az consumption budget create \
  --budget-name "fastapi-api-budget" \
  --amount 200 \
  --time-grain Monthly \
  --start-date "2024-01-01" \
  --end-date "2025-01-01" \
  --notifications key=actual_gte_80_pct threshold=80 contact-emails="ops@company.com"
```

### Application Insights Cost Control

```python
# Configure sampling in Azure — never ingest 100% of traces in prod
# applicationinsights.json
{
  "sampling": {
    "percentage": 10  # 10% sampling = 90% cost reduction
  }
}

# Or in code with OpenTelemetry
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased
sampler = TraceIdRatioBased(0.1)  # 10% sampling rate
```

### Key Metrics to Monitor for Cost Optimization

| Metric | Alert Threshold | Action |
|--------|----------------|--------|
| Function invocations | >50M/day | Review caching, check for loops |
| Avg execution time | >500ms | Profile, optimize, scale up |
| DB connection count | >80% of max | Scale DB tier or add PgBouncer |
| Cache hit rate | <70% | Review TTL strategy, add caching |
| Error rate (5xx) | >1% | Fix bugs → retries amplify cost |
| Egress bandwidth | >5GB/day | Add compression, CDN |

---

## SLA-to-Infrastructure Mapping

| SLA Target | Min Architecture | Estimated Cost/Month |
|-----------|-----------------|---------------------|
| 99% uptime (7h/month downtime OK) | Single Container App instance | $30–60 |
| 99.9% (43min/month) | Container Apps min=2, health checks | $80–150 |
| 99.95% (22min/month) | Container Apps Dedicated + Redis | $200–400 |
| 99.99% (4min/month) | AKS multi-zone + geo-replication | $800–2000+ |

> **Rule**: Each 9 of uptime roughly doubles infrastructure cost. Confirm the actual business SLA before over-engineering.
