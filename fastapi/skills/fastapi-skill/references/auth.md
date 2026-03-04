# Authentication & Authorization Reference

## Table of Contents
1. [Auth Strategy Selection](#auth-strategy-selection)
2. [API Key Auth](#api-key-auth)
3. [JWT Bearer Tokens](#jwt-bearer-tokens)
4. [OAuth2 + OpenID Connect](#oauth2-openid)
5. [Azure AD / Entra ID](#azure-ad)
6. [RBAC — Role-Based Access Control](#rbac)
7. [Multi-Tenant Auth](#multi-tenant)
8. [Security Headers & Best Practices](#security-best-practices)

---

## Auth Strategy Selection

| Strategy | Use when | Complexity |
|---|---|---|
| No auth | Internal network, trusted services | Low |
| API Key | Machine-to-machine, simple clients | Low |
| JWT (HS256) | User sessions, single service | Medium |
| JWT (RS256) | Microservices, token verification without secret | Medium |
| OAuth2 + OIDC | User login, social providers, SSO | High |
| Azure AD / Entra ID | Enterprise, Microsoft ecosystem | High |

---

## API Key Auth

Simple, stateless auth for machine-to-machine.

```python
# core/security.py
import secrets
import hashlib
from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader, APIKeyQuery

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
API_KEY_QUERY = APIKeyQuery(name="api_key", auto_error=False)

def hash_api_key(key: str) -> str:
    """Store hashed keys in DB, never plaintext"""
    return hashlib.sha256(key.encode()).hexdigest()

def generate_api_key() -> str:
    """Generate a cryptographically secure API key"""
    return secrets.token_urlsafe(32)

async def verify_api_key(
    header_key: str | None = Security(API_KEY_HEADER),
    query_key: str | None = Security(API_KEY_QUERY),
    db: AsyncSession = Depends(get_db),
) -> APIKeyRecord:
    key = header_key or query_key
    if not key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    hashed = hash_api_key(key)
    record = await db.execute(
        select(APIKey).where(APIKey.key_hash == hashed, APIKey.is_active == True)
    )
    api_key = record.scalar_one_or_none()

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or expired API key",
        )

    # Update last used timestamp (non-blocking)
    api_key.last_used_at = datetime.now(UTC)
    await db.commit()

    return api_key
```

### Key Rotation Pattern
```python
@app.post("/api-keys/rotate/{key_id}")
async def rotate_api_key(
    key_id: UUID,
    current_key: APIKeyRecord = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db),
):
    new_key = generate_api_key()
    # Store new hash, deactivate old key after grace period
    await db.execute(
        update(APIKey)
        .where(APIKey.id == key_id)
        .values(
            key_hash=hash_api_key(new_key),
            rotated_at=datetime.now(UTC),
        )
    )
    await db.commit()
    return {"api_key": new_key, "warning": "Store this key securely, it will not be shown again"}
```

---

## JWT Bearer Tokens

### Installation
```bash
pip install pyjwt "pwdlib[argon2]"
# For RS256: pip install "pyjwt[crypto]"
```

### Token Models
```python
# schemas/auth.py
from pydantic import BaseModel

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds

class TokenData(BaseModel):
    sub: str          # subject (user id or username)
    scope: str = ""   # space-separated permissions
    jti: str | None = None  # JWT ID (for revocation)
```

### Core Auth Implementation
```python
# core/security.py
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import jwt
from pwdlib import PasswordHash

SECRET_KEY: str  # from settings
ALGORITHM = "HS256"
# For RS256: load private/public keys from PEM files

password_hash = PasswordHash.recommended()
DUMMY_HASH = password_hash.hash("security-dummy-password-for-timing")

def verify_password(plain: str, hashed: str) -> bool:
    return password_hash.verify(plain, hashed)

def get_password_hash(plain: str) -> str:
    return password_hash.hash(plain)

def create_access_token(subject: str, scopes: list[str] = [], ttl_minutes: int = 30) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "scope": " ".join(scopes),
        "iat": now,
        "exp": now + timedelta(minutes=ttl_minutes),
        "jti": str(uuid4()),  # for revocation
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def create_refresh_token(subject: str, ttl_days: int = 7) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "type": "refresh",
        "iat": now,
        "exp": now + timedelta(days=ttl_days),
        "jti": str(uuid4()),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str) -> dict:
    """Raises jwt.PyJWTError on invalid token"""
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
```

### Auth Endpoints
```python
# api/v1/auth.py
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/token", response_model=Token)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: AsyncSession = Depends(get_db),
) -> Token:
    # Look up user
    user = await get_user_by_username(db, form_data.username)
    if not user:
        # Timing attack mitigation: still run hash verify
        verify_password(form_data.password, DUMMY_HASH)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")

    scopes = [user.role]  # e.g., ["admin"] or ["viewer"]
    return Token(
        access_token=create_access_token(str(user.id), scopes),
        refresh_token=create_refresh_token(str(user.id)),
        expires_in=settings.access_token_expire_minutes * 60,
    )

@router.post("/refresh", response_model=Token)
async def refresh_token(refresh: RefreshRequest, db: AsyncSession = Depends(get_db)):
    try:
        payload = decode_token(refresh.refresh_token)
        if payload.get("type") != "refresh":
            raise ValueError("Not a refresh token")
    except (jwt.PyJWTError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    user = await db.get(User, UUID(payload["sub"]))
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    return Token(
        access_token=create_access_token(str(user.id), [user.role]),
        refresh_token=create_refresh_token(str(user.id)),
        expires_in=settings.access_token_expire_minutes * 60,
    )
```

### Auth Dependencies
```python
# dependencies.py
from fastapi.security import OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")

async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: AsyncSession = Depends(get_db),
) -> User:
    try:
        payload = decode_token(token)
        user_id = payload.get("sub")
        if not user_id:
            raise ValueError("Missing subject")
    except (jwt.PyJWTError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await db.get(User, UUID(user_id))
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return user

# Shortcut for endpoints
CurrentUser = Annotated[User, Depends(get_current_user)]
```

---

## OAuth2 + OpenID Connect

For external identity providers (Google, GitHub, Microsoft, Okta):

```bash
pip install "authlib[httpx]"
# or: pip install python-jose[cryptography] httpx
```

```python
# core/oauth.py
from authlib.integrations.starlette_client import OAuth
from starlette.config import Config

config = Config('.env')
oauth = OAuth(config)

oauth.register(
    name='google',
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'},
)

# Route
@app.get("/auth/google")
async def google_login(request: Request):
    redirect_uri = request.url_for('google_callback')
    return await oauth.google.authorize_redirect(request, redirect_uri)

@app.get("/auth/google/callback")
async def google_callback(request: Request):
    token = await oauth.google.authorize_access_token(request)
    user_info = token.get('userinfo')
    # Create or get user from user_info['email']
    # Return JWT token
```

---

## Azure AD / Entra ID

```bash
pip install msal fastapi-azure-auth
```

### Token Validation (Resource Server)
```python
# core/azure_auth.py
from fastapi_azure_auth import SingleTenantAzureAuthorizationCodeBearer

azure_scheme = SingleTenantAzureAuthorizationCodeBearer(
    app_client_id=settings.azure_client_id,
    tenant_id=settings.azure_tenant_id,
    scopes={
        f"api://{settings.azure_client_id}/access_as_user": "Access API",
    },
)

# Group-based RBAC
def require_azure_group(group_id: str):
    async def _check(token: dict = Security(azure_scheme)):
        groups = token.get("groups", [])
        if group_id not in groups:
            raise HTTPException(403, "Insufficient group membership")
        return token
    return _check

# Usage
@app.get("/admin/")
async def admin_only(
    token: dict = Depends(require_azure_group("admin-group-object-id"))
):
    ...
```

---

## RBAC — Role-Based Access Control

### Simple Role Dependency

```python
# dependencies.py
from enum import Enum

class UserRole(str, Enum):
    admin = "admin"
    editor = "editor"
    viewer = "viewer"

def require_roles(*roles: UserRole):
    """Factory that creates a dependency checking user role"""
    async def _dependency(current_user: CurrentUser) -> User:
        if current_user.role not in [r.value for r in roles]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role {current_user.role!r} not authorized. Required: {[r.value for r in roles]}",
            )
        return current_user
    return Depends(_dependency)

# Usage
@app.delete("/users/{id}", dependencies=[require_roles(UserRole.admin)])
async def delete_user(id: UUID): ...

@app.put("/items/{id}")
async def update_item(
    id: UUID,
    item: ItemUpdate,
    user: User = require_roles(UserRole.admin, UserRole.editor),
): ...
```

### Permission-Based (Fine-Grained)

```python
from enum import auto, Flag

class Permission(Flag):
    READ = auto()
    WRITE = auto()
    DELETE = auto()
    ADMIN = READ | WRITE | DELETE

ROLE_PERMISSIONS = {
    "admin": Permission.ADMIN,
    "editor": Permission.READ | Permission.WRITE,
    "viewer": Permission.READ,
}

def require_permission(permission: Permission):
    async def _check(current_user: CurrentUser) -> User:
        user_perms = ROLE_PERMISSIONS.get(current_user.role, Permission(0))
        if not (user_perms & permission):
            raise HTTPException(403, f"Permission {permission.name} required")
        return current_user
    return Depends(_check)
```

---

## Multi-Tenant Auth

For SaaS applications where users belong to organizations:

```python
# Tenant resolution middleware
@app.middleware("http")
async def resolve_tenant(request: Request, call_next):
    # From subdomain: tenant.myapp.com
    host = request.headers.get("host", "")
    tenant_slug = host.split(".")[0] if "." in host else None

    # Or from header: X-Tenant-ID
    tenant_id = request.headers.get("x-tenant-id") or tenant_slug

    if tenant_id:
        request.state.tenant_id = tenant_id
    return await call_next(request)

# Tenant-scoped dependency
async def get_tenant(request: Request, db: AsyncSession = Depends(get_db)) -> Tenant:
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(400, "Tenant not specified")
    tenant = await db.execute(select(Tenant).where(Tenant.slug == tenant_id))
    tenant = tenant.scalar_one_or_none()
    if not tenant:
        raise HTTPException(404, "Tenant not found")
    return tenant
```

---

## Security Headers & Best Practices

### Security Middleware

```python
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.middleware.cors import CORSMiddleware

# Production security headers middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.update({
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "geolocation=(), microphone=()",
    })
    return response

# CORS (add before security headers middleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
    expose_headers=["X-Total-Count", "X-Request-ID"],
)

# Only in production
if not settings.debug:
    app.add_middleware(HTTPSRedirectMiddleware)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
```

### Rate Limiting

```bash
pip install slowapi
```

```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.post("/auth/token")
@limiter.limit("5/minute")  # brute force protection on auth
async def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends()):
    ...
```
