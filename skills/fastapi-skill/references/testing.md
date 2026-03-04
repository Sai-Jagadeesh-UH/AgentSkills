# Testing Reference — FastAPI

## Table of Contents
1. [Test Setup & Configuration](#setup)
2. [Async Test Patterns](#async-tests)
3. [Fixtures](#fixtures)
4. [Auth in Tests](#auth-tests)
5. [Database Testing](#database-testing)
6. [Mocking External Services](#mocking)
7. [Integration & E2E Tests](#integration)
8. [Test Organization](#organization)

---

## Test Setup & Configuration {#setup}

### Installation

```bash
pip install pytest pytest-asyncio anyio httpx
# Optional extras
pip install pytest-cov polyfactory faker pytest-mock
```

### pytest.ini / pyproject.toml

```toml
# pyproject.toml
[tool.pytest.ini_options]
asyncio_mode = "auto"          # auto-detect async tests
testpaths = ["tests"]
filterwarnings = [
    "error",
    "ignore::DeprecationWarning",
]
markers = [
    "integration: marks tests as integration (may require external services)",
    "slow: marks tests as slow",
]

[tool.coverage.run]
source = ["app"]
omit = ["*/tests/*", "*/migrations/*"]
```

### Test Directory Structure

```
tests/
├── conftest.py          ← global fixtures (app, client, db)
├── test_api/
│   ├── conftest.py      ← API-specific fixtures
│   ├── test_auth.py
│   ├── test_users.py
│   └── test_items.py
├── test_services/
│   ├── test_user_service.py
│   └── test_item_service.py
└── test_repositories/
    └── test_user_repo.py
```

---

## Async Test Patterns {#async-tests}

### Basic Async Test

```python
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app

@pytest.mark.asyncio
async def test_health():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
```

### Using anyio (preferred — works with all async backends)

```python
import pytest
import anyio
from httpx import AsyncClient, ASGITransport

# Auto-marks all async tests with anyio
@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"

@pytest.mark.anyio
async def test_create_user(client: AsyncClient):
    response = await client.post("/api/v1/users/", json={
        "email": "new@example.com",
        "password": "SecurePass1",
        "full_name": "Test User",
    })
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "new@example.com"
    assert "password" not in data  # ensure password not leaked
```

---

## Fixtures {#fixtures}

### Core conftest.py

```python
# tests/conftest.py
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.main import app
from app.core.database import Base, get_db
from app.config import get_settings

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"

@pytest_asyncio.fixture(scope="session")
async def db_engine():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()

@pytest_asyncio.fixture
async def db_session(db_engine):
    """Each test gets an isolated transaction that's rolled back after"""
    TestSession = async_sessionmaker(db_engine, expire_on_commit=False)
    async with TestSession() as session:
        # Begin a savepoint for rollback isolation
        async with session.begin_nested():
            yield session
        await session.rollback()

@pytest_asyncio.fixture
async def client(db_session: AsyncSession):
    """HTTP client with DB dependency overridden to use test session"""
    app.dependency_overrides[get_db] = lambda: db_session
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac
    app.dependency_overrides.clear()
```

### User and Auth Fixtures

```python
# tests/conftest.py (continued)

@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> User:
    from app.services.user import create_user
    user = await create_user(db_session, UserCreate(
        email="test@example.com",
        password="TestPassword1",
        full_name="Test User",
    ))
    return user

@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> User:
    from app.services.user import create_user
    user = await create_user(db_session, UserCreate(
        email="admin@example.com",
        password="AdminPassword1",
        full_name="Admin User",
        role="admin",
    ))
    return user

@pytest.fixture
def auth_headers(test_user: User) -> dict[str, str]:
    from app.core.security import create_access_token
    token = create_access_token(str(test_user.id))
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture
def admin_headers(admin_user: User) -> dict[str, str]:
    from app.core.security import create_access_token
    token = create_access_token(str(admin_user.id))
    return {"Authorization": f"Bearer {token}"}
```

### Factory Fixtures with polyfactory

```python
# tests/factories.py
from polyfactory.factories.pydantic_factory import ModelFactory
from app.schemas.user import UserCreate
from app.schemas.item import ItemCreate
import random

class UserFactory(ModelFactory):
    __model__ = UserCreate

    email = lambda: f"user_{random.randint(1, 99999)}@test.com"
    password = "SecureTest123!"
    full_name = "Generated User"

class ItemFactory(ModelFactory):
    __model__ = ItemCreate

    name = "Test Item"
    price = lambda: round(random.uniform(1, 1000), 2)

# Usage in tests
def test_bulk_create(client, auth_headers):
    users = UserFactory.batch(10)
    # ...
```

---

## Auth in Tests {#auth-tests}

### Testing Auth Endpoints

```python
# tests/test_api/test_auth.py
import pytest
from httpx import AsyncClient

@pytest.mark.anyio
async def test_login_success(client: AsyncClient, test_user: User):
    response = await client.post("/api/v1/auth/token", data={
        "username": test_user.email,
        "password": "TestPassword1",
    })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

@pytest.mark.anyio
async def test_login_wrong_password(client: AsyncClient, test_user: User):
    response = await client.post("/api/v1/auth/token", data={
        "username": test_user.email,
        "password": "WrongPassword",
    })
    assert response.status_code == 401

@pytest.mark.anyio
async def test_protected_endpoint_no_token(client: AsyncClient):
    response = await client.get("/api/v1/users/me")
    assert response.status_code == 401

@pytest.mark.anyio
async def test_protected_endpoint_with_token(
    client: AsyncClient,
    auth_headers: dict,
    test_user: User,
):
    response = await client.get("/api/v1/users/me", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["email"] == test_user.email

@pytest.mark.anyio
async def test_admin_only_forbidden(client: AsyncClient, auth_headers: dict):
    """Regular user cannot access admin endpoint"""
    response = await client.delete("/api/v1/users/some-id", headers=auth_headers)
    assert response.status_code == 403

@pytest.mark.anyio
async def test_admin_only_allowed(client: AsyncClient, admin_headers: dict):
    """Admin can access admin endpoint"""
    response = await client.get("/api/v1/admin/users", headers=admin_headers)
    assert response.status_code == 200
```

---

## Database Testing {#database-testing}

### Repository Tests

```python
# tests/test_repositories/test_user_repo.py
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.user import UserRepository

@pytest.mark.anyio
async def test_create_user(db_session: AsyncSession):
    repo = UserRepository(db_session)
    user = await repo.create(UserCreate(
        email="repo_test@example.com",
        full_name="Repo Test",
    ), hashed_password="hashed")

    assert user.id is not None
    assert user.email == "repo_test@example.com"

@pytest.mark.anyio
async def test_get_by_email(db_session: AsyncSession, test_user: User):
    repo = UserRepository(db_session)
    found = await repo.get_by_email(test_user.email)
    assert found is not None
    assert found.id == test_user.id

@pytest.mark.anyio
async def test_list_paginated(db_session: AsyncSession):
    repo = UserRepository(db_session)
    # Create 25 users
    for i in range(25):
        await repo.create(
            UserCreate(email=f"page_user_{i}@test.com", full_name=f"User {i}"),
            hashed_password="hashed"
        )

    users, total = await repo.list_paginated(page=1, size=10)
    assert len(users) == 10
    assert total >= 25

    users_p2, _ = await repo.list_paginated(page=2, size=10)
    assert len(users_p2) == 10
    # Ensure no duplicates between pages
    p1_ids = {u.id for u in users}
    p2_ids = {u.id for u in users_p2}
    assert p1_ids.isdisjoint(p2_ids)
```

---

## Mocking External Services {#mocking}

### pytest-mock for async services

```python
@pytest.mark.anyio
async def test_create_user_sends_email(
    client: AsyncClient,
    auth_headers: dict,
    mocker,
):
    mock_send = mocker.patch(
        "app.services.email.send_welcome_email",
        return_value=None,
    )

    response = await client.post("/api/v1/users/", json={
        "email": "newuser@example.com",
        "password": "NewPass1!",
        "full_name": "New User",
    })
    assert response.status_code == 201
    mock_send.assert_called_once_with("newuser@example.com", "New User")
```

### Mocking httpx external calls

```python
import respx
import httpx

@pytest.mark.anyio
async def test_external_api_call(client: AsyncClient, auth_headers: dict):
    with respx.mock(base_url="https://external-api.example.com") as mock:
        mock.get("/data").mock(
            return_value=httpx.Response(200, json={"key": "value"})
        )
        response = await client.get("/api/v1/enriched-data", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["external_key"] == "value"
```

---

## Integration & E2E Tests {#integration}

```python
# tests/integration/test_full_flow.py
@pytest.mark.integration
@pytest.mark.anyio
async def test_complete_user_flow(client: AsyncClient):
    """Test complete signup → login → create item → read item flow"""

    # 1. Register
    reg = await client.post("/api/v1/auth/register", json={
        "email": "flow_test@example.com",
        "password": "FlowTest123!",
        "full_name": "Flow Test User",
    })
    assert reg.status_code == 201

    # 2. Login
    login = await client.post("/api/v1/auth/token", data={
        "username": "flow_test@example.com",
        "password": "FlowTest123!",
    })
    assert login.status_code == 200
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 3. Create item
    create = await client.post("/api/v1/items/", json={
        "name": "Test Item",
        "price": 29.99,
    }, headers=headers)
    assert create.status_code == 201
    item_id = create.json()["id"]

    # 4. Read item
    read = await client.get(f"/api/v1/items/{item_id}", headers=headers)
    assert read.status_code == 200
    assert read.json()["name"] == "Test Item"

    # 5. Delete item
    delete = await client.delete(f"/api/v1/items/{item_id}", headers=headers)
    assert delete.status_code == 204

    # 6. Confirm deleted
    not_found = await client.get(f"/api/v1/items/{item_id}", headers=headers)
    assert not_found.status_code == 404
```

---

## Test Organization {#organization}

### Run Commands

```bash
# All tests
pytest

# With coverage
pytest --cov=app --cov-report=html --cov-report=term-missing

# Only unit tests (exclude integration)
pytest -m "not integration"

# Only specific file
pytest tests/test_api/test_users.py -v

# Only specific test
pytest tests/test_api/test_users.py::test_create_user -v

# Parallel execution (pip install pytest-xdist)
pytest -n auto

# Stop on first failure
pytest -x

# Show local variables on failure
pytest -l
```

### Validation Tests (Pydantic)

```python
# tests/test_schemas/test_user_schema.py
import pytest
from pydantic import ValidationError
from app.schemas.user import UserCreate

def test_valid_user():
    user = UserCreate(email="valid@example.com", password="Valid1pass!", full_name="Valid")
    assert user.email == "valid@example.com"

def test_invalid_email():
    with pytest.raises(ValidationError) as exc:
        UserCreate(email="not-an-email", password="Valid1!", full_name="Test")
    assert "email" in str(exc.value)

def test_weak_password():
    with pytest.raises(ValidationError) as exc:
        UserCreate(email="ok@example.com", password="weak", full_name="Test")
    assert "password" in str(exc.value)

def test_password_not_in_response():
    from app.schemas.user import UserRead
    user_read = UserRead(id=1, email="a@b.com", full_name="A", is_active=True,
                         created_at=datetime.now())
    data = user_read.model_dump()
    assert "password" not in data
    assert "hashed_password" not in data
```
