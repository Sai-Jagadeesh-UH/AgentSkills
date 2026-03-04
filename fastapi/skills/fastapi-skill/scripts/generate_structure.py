#!/usr/bin/env python3
"""
FastAPI Project Structure Generator
Scaffolds a new FastAPI project with the correct modular structure.

Usage:
    python skills/fastapi-skill/scripts/generate_structure.py \
        --name my-api \
        --target uvicorn \
        --db postgresql \
        --auth jwt \
        --ui none

Options:
    --name       Project/package name (snake_case)
    --target     Deployment target: uvicorn | gunicorn | docker | azure-function | lambda | container-app
    --db         Database: postgresql | sqlite | mongodb | none
    --auth       Authentication: jwt | apikey | azure-ad | oauth2 | none
    --ui         UI layer: nicegui | jinja2 | none
    --out        Output directory (default: current directory)
"""

import argparse
import os
import sys
from pathlib import Path
from textwrap import dedent


def snake_case(name: str) -> str:
    return name.lower().replace("-", "_").replace(" ", "_")


def pascal_case(name: str) -> str:
    return "".join(word.capitalize() for word in name.replace("-", "_").split("_"))


def create_file(path: Path, content: str, overwrite: bool = False):
    if path.exists() and not overwrite:
        print(f"  ⏭️  Skipped (exists): {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dedent(content).lstrip())
    print(f"  ✅ Created: {path}")


def generate_main_py(app_name: str, has_db: bool, has_redis: bool, ui: str) -> str:
    lifespan_imports = []
    lifespan_startup = []
    lifespan_shutdown = []
    app_kwargs = []

    if has_db:
        lifespan_startup.append(
            "    # Initialize DB connection pool\n"
            "    from app.core.database import engine, Base\n"
            "    async with engine.begin() as conn:\n"
            "        pass  # Pool is ready\n"
            "    logger.info('Database connection pool ready')"
        )
        lifespan_shutdown.append(
            "    from app.core.database import engine\n"
            "    await engine.dispose()\n"
            "    logger.info('Database connection pool closed')"
        )

    if has_redis:
        lifespan_startup.append(
            "    # Initialize Redis\n"
            "    import redis.asyncio as aioredis\n"
            "    app.state.redis = aioredis.from_url(settings.redis_url)\n"
            "    logger.info('Redis connection ready')"
        )
        lifespan_shutdown.append(
            "    await app.state.redis.close()\n"
            "    logger.info('Redis connection closed')"
        )

    startup_block = "\n\n".join(lifespan_startup) if lifespan_startup else "    pass"
    shutdown_block = "\n\n".join(lifespan_shutdown) if lifespan_shutdown else "    pass"

    return f'''from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import get_settings
from app.api.router import api_router
from app.exceptions import register_exception_handlers

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""
    logger.info(f"Starting {{settings.app_name}} v{{settings.app_version}}")
{startup_block}
    yield
{shutdown_block}
    logger.info("Application shutdown complete")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="FastAPI REST API",
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url=None,
)

# Middleware (order matters — last added = outermost)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(api_router)

# Exception handlers
register_exception_handlers(app)
'''


def generate_config_py(has_db: bool, has_redis: bool, has_azure: bool) -> str:
    fields = [
        "    # Application",
        "    app_name: str = 'FastAPI App'",
        "    app_version: str = '1.0.0'",
        "    environment: str = 'production'",
        "    debug: bool = False",
        "",
        "    # Security — generate with: openssl rand -hex 32",
        "    secret_key: SecretStr",
        "    algorithm: str = 'HS256'",
        "    access_token_expire_minutes: int = 30",
        "",
        "    # CORS",
        "    allowed_origins: list[str] = ['http://localhost:3000']",
    ]

    if has_db:
        fields += [
            "",
            "    # Database",
            "    database_url: str",
            "    db_pool_size: int = 10",
            "    db_max_overflow: int = 20",
        ]

    if has_redis:
        fields += [
            "",
            "    # Redis",
            "    redis_url: str | None = None",
            "    cache_ttl_seconds: int = 300",
        ]

    if has_azure:
        fields += [
            "",
            "    # Azure",
            "    azure_tenant_id: str | None = None",
            "    azure_client_id: str | None = None",
        ]

    fields_str = "\n".join(fields)

    return f'''from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

{fields_str}


@lru_cache
def get_settings() -> Settings:
    return Settings()
'''


def generate_database_py() -> str:
    return '''from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)
from sqlalchemy.orm import DeclarativeBase
from app.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=settings.debug,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
'''


def generate_security_py(auth: str) -> str:
    if auth == "jwt":
        return '''from datetime import datetime, timedelta, timezone
from uuid import uuid4
import jwt
from pwdlib import PasswordHash
from app.config import get_settings

settings = get_settings()
password_hash = PasswordHash.recommended()
DUMMY_HASH = password_hash.hash("security-dummy-for-timing-attack-prevention")


def verify_password(plain: str, hashed: str) -> bool:
    return password_hash.verify(plain, hashed)


def get_password_hash(plain: str) -> str:
    return password_hash.hash(plain)


def create_access_token(subject: str, scopes: list[str] = [], ttl_minutes: int | None = None) -> str:
    ttl = ttl_minutes or settings.access_token_expire_minutes
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "scope": " ".join(scopes),
        "iat": now,
        "exp": now + timedelta(minutes=ttl),
        "jti": str(uuid4()),
    }
    return jwt.encode(payload, settings.secret_key.get_secret_value(), algorithm=settings.algorithm)


def decode_token(token: str) -> dict:
    """Raises jwt.PyJWTError on invalid/expired token."""
    return jwt.decode(
        token,
        settings.secret_key.get_secret_value(),
        algorithms=[settings.algorithm],
    )
'''
    elif auth == "apikey":
        return '''import secrets
import hashlib
from app.config import get_settings

settings = get_settings()


def generate_api_key() -> str:
    """Generate a cryptographically secure API key."""
    return secrets.token_urlsafe(32)


def hash_api_key(key: str) -> str:
    """Hash an API key for storage. Never store plaintext."""
    return hashlib.sha256(key.encode()).hexdigest()
'''
    else:
        return '''# No authentication configured
# Add security functions here as needed
'''


def generate_exceptions_py() -> str:
    return '''from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def register_exception_handlers(app: FastAPI):
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.detail,
                "request_id": getattr(request.state, "request_id", None),
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        details = []
        for error in exc.errors():
            field = ".".join(str(loc) for loc in error["loc"] if loc != "body")
            details.append({"field": field, "message": error["msg"], "code": error["type"]})

        return JSONResponse(
            status_code=422,
            content={
                "error": "Validation failed",
                "details": details,
                "request_id": getattr(request.state, "request_id", None),
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        import logging
        logging.getLogger(__name__).exception("Unhandled exception", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error"},
        )
'''


def generate_dependencies_py(auth: str) -> str:
    if auth == "jwt":
        return '''from typing import Annotated
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import decode_token
import jwt

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: AsyncSession = Depends(get_db),
):
    """Dependency: validates JWT and returns current user."""
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

    # TODO: Replace with actual user lookup from DB
    # from app.repositories.user import UserRepository
    # repo = UserRepository(db)
    # user = await repo.get_by_id(user_id)
    # if not user:
    #     raise HTTPException(404, "User not found")
    # return user

    return {"id": user_id}  # placeholder


# Type alias for cleaner endpoint signatures
CurrentUser = Annotated[dict, Depends(get_current_user)]
'''
    elif auth == "apikey":
        return '''from typing import Annotated
from fastapi import Security, HTTPException, Depends, status
from fastapi.security import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import hash_api_key

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(
    api_key: str | None = Security(api_key_header),
    db: AsyncSession = Depends(get_db),
):
    """Dependency: validates X-API-Key header."""
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-API-Key header required",
        )

    key_hash = hash_api_key(api_key)
    # TODO: Look up hashed key in database
    # record = await db.execute(select(APIKey).where(APIKey.key_hash == key_hash))
    # if not record.scalar_one_or_none():
    #     raise HTTPException(403, "Invalid API key")

    return {"key_hash": key_hash}  # placeholder
'''
    else:
        return '''from typing import Annotated
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db

# Add authentication dependencies here when needed
# See references/auth.md for implementation patterns

DB = Annotated[AsyncSession, Depends(get_db)]
'''


def generate_health_py() -> str:
    return '''from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone
from fastapi.responses import JSONResponse
from app.core.database import get_db

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health():
    """Liveness check — always 200 if process is alive."""
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/ready")
async def readiness(db: AsyncSession = Depends(get_db)):
    """Readiness check — verifies DB connectivity."""
    checks = {}
    status = "ready"

    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e}"
        status = "not_ready"

    code = 200 if status == "ready" else 503
    return JSONResponse(
        status_code=code,
        content={"status": status, "checks": checks},
    )
'''


def generate_api_router(has_auth: bool) -> str:
    auth_import = "from app.api.v1 import auth, " if has_auth else "from app.api.v1 import "
    auth_include = "    v1_router.include_router(auth.router, prefix='/auth', tags=['Auth'])\n" if has_auth else ""

    return f'''from fastapi import APIRouter
from app.api import health
{auth_import}items  # Add more domain routers here

api_router = APIRouter()

# Health endpoints (no version prefix)
api_router.include_router(health.router)

# Versioned API
v1_router = APIRouter(prefix="/api/v1")
{auth_include}v1_router.include_router(items.router, prefix="/items", tags=["Items"])

api_router.include_router(v1_router)
'''


def generate_env_example(has_db: bool, has_redis: bool, has_azure: bool) -> str:
    lines = [
        "# Application",
        "APP_NAME=FastAPI App",
        "APP_VERSION=1.0.0",
        "ENVIRONMENT=production",
        "DEBUG=false",
        "",
        "# Security — generate with: openssl rand -hex 32",
        "SECRET_KEY=CHANGE_ME_GENERATE_WITH_OPENSSL",
        "ALGORITHM=HS256",
        "ACCESS_TOKEN_EXPIRE_MINUTES=30",
        "",
        "# CORS",
        'ALLOWED_ORIGINS=["http://localhost:3000"]',
    ]

    if has_db:
        lines += [
            "",
            "# Database",
            "DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/dbname",
            "DB_POOL_SIZE=10",
            "DB_MAX_OVERFLOW=20",
        ]

    if has_redis:
        lines += [
            "",
            "# Redis",
            "REDIS_URL=redis://localhost:6379/0",
            "CACHE_TTL_SECONDS=300",
        ]

    if has_azure:
        lines += [
            "",
            "# Azure",
            "AZURE_TENANT_ID=",
            "AZURE_CLIENT_ID=",
        ]

    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Generate FastAPI project structure")
    parser.add_argument("--name", required=True, help="Project name (snake_case)")
    parser.add_argument("--target", default="uvicorn",
                        choices=["uvicorn", "gunicorn", "docker", "azure-function", "lambda", "container-app"])
    parser.add_argument("--db", default="postgresql",
                        choices=["postgresql", "sqlite", "mongodb", "none"])
    parser.add_argument("--auth", default="jwt",
                        choices=["jwt", "apikey", "azure-ad", "oauth2", "none"])
    parser.add_argument("--ui", default="none",
                        choices=["nicegui", "jinja2", "none"])
    parser.add_argument("--out", default=".", help="Output directory")
    args = parser.parse_args()

    app_name = snake_case(args.name)
    out_dir = Path(args.out)
    has_db = args.db != "none"
    has_redis = args.target in ["docker", "container-app"]
    has_azure = args.target in ["azure-function", "container-app"] or args.auth == "azure-ad"

    print(f"\n🚀 Generating FastAPI project: {app_name}")
    print(f"   Target: {args.target}")
    print(f"   Database: {args.db}")
    print(f"   Auth: {args.auth}")
    print(f"   UI: {args.ui}")
    print(f"   Output: {out_dir.resolve()}\n")

    # Generate all files
    create_file(out_dir / "app/__init__.py", "")
    create_file(out_dir / "app/main.py",
                generate_main_py(app_name, has_db, has_redis, args.ui))
    create_file(out_dir / "app/config.py",
                generate_config_py(has_db, has_redis, has_azure))
    create_file(out_dir / "app/exceptions.py", generate_exceptions_py())
    create_file(out_dir / "app/dependencies.py", generate_dependencies_py(args.auth))

    # Core
    create_file(out_dir / "app/core/__init__.py", "")
    create_file(out_dir / "app/core/security.py", generate_security_py(args.auth))
    if has_db:
        create_file(out_dir / "app/core/database.py", generate_database_py())

    # API structure
    create_file(out_dir / "app/api/__init__.py", "")
    create_file(out_dir / "app/api/router.py", generate_api_router(args.auth != "none"))
    create_file(out_dir / "app/api/health.py", generate_health_py())
    create_file(out_dir / "app/api/v1/__init__.py", "")

    # Domain placeholders
    for domain in ["schemas", "models", "services", "repositories"]:
        create_file(out_dir / f"app/{domain}/__init__.py", "")

    # Tests
    create_file(out_dir / "tests/__init__.py", "")
    create_file(out_dir / "tests/conftest.py", "# Add test fixtures here\n# See references/testing.md\n")
    create_file(out_dir / "tests/test_api/__init__.py", "")

    # Config files
    create_file(out_dir / ".env.example",
                generate_env_example(has_db, has_redis, has_azure))
    create_file(out_dir / ".gitignore",
                ".env\n.env.*\n!.env.example\n__pycache__/\n*.pyc\n.venv/\nvenv/\n.pytest_cache/\n")

    print(f"\n✅ Project structure generated in: {out_dir.resolve()}")
    print("\nNext steps:")
    print("  1. Copy .env.example to .env and fill in values")
    print(f"  2. Install deps: pip install 'fastapi[standard]' pydantic-settings")
    if has_db:
        print(f"  3. Install DB deps: pip install sqlalchemy[asyncio] asyncpg alembic")
    if args.auth == "jwt":
        print(f"  4. Install auth deps: pip install pyjwt 'pwdlib[argon2]'")
    print(f"  5. Run dev server: uvicorn app.main:app --reload")
    print(f"  6. View docs at: http://localhost:8000/docs")


if __name__ == "__main__":
    main()
