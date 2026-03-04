# Pydantic v2 Patterns Reference

## Table of Contents
1. [Schema Separation Pattern](#schema-separation)
2. [Base Model Hierarchies](#base-model-hierarchies)
3. [Validation Patterns](#validation-patterns)
4. [ORM Integration](#orm-integration)
5. [Complex Field Types](#complex-field-types)
6. [Settings Management](#settings-management)
7. [Common Pitfalls](#common-pitfalls)
8. [Interactive Model Design Checklist](#interactive-checklist)

---

## Schema Separation Pattern

Always separate **ORM models** (SQLAlchemy/SQLModel) from **API schemas** (Pydantic). This prevents leaking internal fields, allows independent evolution, and enables response shaping.

```
models/
└── user.py         ← SQLAlchemy ORM model (database table)
schemas/
└── user.py         ← Pydantic schemas (API request/response)
```

### Naming Convention

```python
# schemas/user.py

class UserBase(BaseModel):
    """Shared fields between create and read"""
    email: EmailStr
    full_name: str
    is_active: bool = True

class UserCreate(UserBase):
    """Fields required when creating a user (includes password)"""
    password: str

class UserUpdate(BaseModel):
    """All fields optional for partial updates (PATCH)"""
    email: EmailStr | None = None
    full_name: str | None = None
    is_active: bool | None = None
    password: str | None = None

class UserRead(UserBase):
    """Fields returned by API (excludes password)"""
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class UserReadWithPosts(UserRead):
    """Extended read with nested relations"""
    posts: list[PostRead] = []
```

---

## Base Model Hierarchies

Use a shared `AppBaseModel` to enforce project-wide conventions:

```python
# schemas/base.py
from pydantic import BaseModel, ConfigDict
from datetime import datetime

class AppBaseModel(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,      # ORM compatibility
        populate_by_name=True,     # accept field name AND alias
        str_strip_whitespace=True, # auto-strip leading/trailing whitespace
        use_enum_values=True,      # store .value not the enum itself
        validate_default=True,     # validate fields with defaults too
    )

class TimestampMixin(AppBaseModel):
    created_at: datetime
    updated_at: datetime

class PaginatedResponse(AppBaseModel):
    """Generic paginated response wrapper"""
    items: list
    total: int
    page: int
    size: int
    pages: int
```

### Generic Paginated Response

```python
from typing import Generic, TypeVar
from pydantic import BaseModel

T = TypeVar("T")

class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    size: int

    @property
    def pages(self) -> int:
        return (self.total + self.size - 1) // self.size

# Usage
@app.get("/users/", response_model=Page[UserRead])
async def list_users(page: int = 1, size: int = 20):
    ...
```

---

## Validation Patterns

### Field Constraints

```python
from pydantic import BaseModel, Field
from typing import Annotated

class Product(BaseModel):
    # String constraints
    name: Annotated[str, Field(min_length=1, max_length=200, pattern=r'^[a-zA-Z0-9 ]+$')]
    slug: Annotated[str, Field(min_length=1, max_length=100, pattern=r'^[a-z0-9-]+$')]

    # Numeric constraints
    price: Annotated[float, Field(gt=0, le=999999.99, multiple_of=0.01)]
    stock: Annotated[int, Field(ge=0, le=100000)]
    discount_pct: Annotated[float, Field(ge=0.0, le=100.0, default=0.0)]

    # List constraints
    tags: Annotated[list[str], Field(min_length=0, max_length=10, default_factory=list)]
    images: Annotated[list[HttpUrl], Field(max_length=5, default_factory=list)]
```

### Field Validators

```python
from pydantic import field_validator

class UserCreate(BaseModel):
    username: str
    password: str
    confirm_password: str

    @field_validator('username')
    @classmethod
    def username_alphanumeric(cls, v: str) -> str:
        if not v.replace('_', '').replace('-', '').isalnum():
            raise ValueError('username must be alphanumeric (underscores and hyphens allowed)')
        return v.lower()

    @field_validator('password')
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError('password must be at least 8 characters')
        if not any(c.isupper() for c in v):
            raise ValueError('password must contain at least one uppercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('password must contain at least one digit')
        return v
```

### Model Validators (Cross-Field)

```python
from pydantic import model_validator
from typing import Self

class DateRange(BaseModel):
    start_date: date
    end_date: date

    @model_validator(mode='after')
    def end_after_start(self) -> Self:
        if self.end_date <= self.start_date:
            raise ValueError('end_date must be after start_date')
        return self

class PasswordConfirm(BaseModel):
    password: str
    confirm_password: str

    @model_validator(mode='after')
    def passwords_match(self) -> Self:
        if self.password != self.confirm_password:
            raise ValueError('passwords do not match')
        return self

    def model_post_init(self, __context) -> None:
        # Clear confirm_password after validation
        del self.confirm_password
```

### Alias and Serialization Aliases

```python
from pydantic import BaseModel, Field, AliasPath, AliasChoices

class ExternalAPI(BaseModel):
    # Accept snake_case or camelCase from external JSON
    user_id: int = Field(
        validation_alias=AliasChoices('user_id', 'userId', 'uid')
    )
    # Serialize response as camelCase
    full_name: str = Field(serialization_alias='fullName')
    created_at: datetime = Field(serialization_alias='createdAt')

    model_config = ConfigDict(populate_by_name=True)

# Deep path alias for nested JSON
class Nested(BaseModel):
    city: str = Field(validation_alias=AliasPath('address', 'city'))
    # Parses: {"address": {"city": "NYC"}}
```

---

## ORM Integration

### SQLAlchemy Async + Pydantic v2

```python
# models/user.py (SQLAlchemy)
from sqlalchemy import String, Boolean, DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from datetime import datetime, UTC

class Base(DeclarativeBase):
    pass

class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

# schemas/user.py (Pydantic)
class UserRead(AppBaseModel):
    id: int
    email: EmailStr
    full_name: str
    is_active: bool
    created_at: datetime
    # model_config includes from_attributes=True via AppBaseModel

# Usage in endpoint
user_orm = await db.get(UserModel, user_id)
user_schema = UserRead.model_validate(user_orm)  # ORM → Pydantic
```

### SQLModel (Unified Approach)

```python
# SQLModel combines SQLAlchemy + Pydantic in one class
from sqlmodel import SQLModel, Field
from datetime import datetime

class UserBase(SQLModel):
    email: str = Field(index=True, unique=True)
    full_name: str = Field(max_length=100)

class User(UserBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    hashed_password: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

class UserCreate(UserBase):
    password: str

class UserRead(UserBase):
    id: int
    created_at: datetime
```

---

## Complex Field Types

### Enums

```python
from enum import Enum
from pydantic import BaseModel

class UserRole(str, Enum):
    admin = "admin"
    editor = "editor"
    viewer = "viewer"

class Status(str, Enum):
    active = "active"
    inactive = "inactive"
    pending = "pending"

class User(BaseModel):
    role: UserRole = UserRole.viewer
    status: Status = Status.pending
```

### UUID Fields

```python
from uuid import UUID, uuid4
from pydantic import BaseModel, Field

class Resource(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    external_id: UUID
```

### Nested Models with Discriminated Unions

```python
from typing import Annotated, Literal, Union
from pydantic import BaseModel, Field

class EmailNotification(BaseModel):
    type: Literal["email"]
    to_address: EmailStr
    subject: str
    body: str

class SMSNotification(BaseModel):
    type: Literal["sms"]
    phone_number: str
    message: str

class PushNotification(BaseModel):
    type: Literal["push"]
    device_token: str
    title: str
    body: str

Notification = Annotated[
    Union[EmailNotification, SMSNotification, PushNotification],
    Field(discriminator="type")
]

class NotificationRequest(BaseModel):
    notification: Notification
    scheduled_at: datetime | None = None
```

### Custom Types

```python
from pydantic import GetCoreSchemaHandler
from pydantic_core import core_schema
from typing import Any

class PhoneNumber(str):
    """Custom type with Pydantic v2 validation"""

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        return core_schema.with_info_plain_validator_function(cls._validate)

    @classmethod
    def _validate(cls, value: Any, info: Any) -> 'PhoneNumber':
        if not isinstance(value, str):
            raise ValueError("Phone number must be a string")
        cleaned = ''.join(filter(str.isdigit, value))
        if len(cleaned) < 10 or len(cleaned) > 15:
            raise ValueError("Invalid phone number length")
        return cls(f"+{cleaned}")
```

---

## Settings Management

Use `pydantic-settings` for environment-based configuration:

```python
# config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import PostgresDsn, RedisDsn, SecretStr
from functools import lru_cache

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "My API"
    app_version: str = "1.0.0"
    debug: bool = False
    environment: str = "production"

    # Security
    secret_key: SecretStr
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # Database
    database_url: PostgresDsn
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # Redis (optional)
    redis_url: RedisDsn | None = None
    cache_ttl_seconds: int = 300

    # CORS
    allowed_origins: list[str] = ["http://localhost:3000"]
    allowed_methods: list[str] = ["*"]
    allowed_headers: list[str] = ["*"]

    # Azure (optional)
    azure_tenant_id: str | None = None
    azure_client_id: str | None = None

@lru_cache
def get_settings() -> Settings:
    return Settings()

# Usage in dependency
from fastapi import Depends
settings: Settings = Depends(get_settings)
```

**.env.example**
```env
SECRET_KEY=generate-with-openssl-rand-hex-32
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/dbname
REDIS_URL=redis://localhost:6379/0
DEBUG=false
ENVIRONMENT=production
ALLOWED_ORIGINS=["https://myapp.com","https://www.myapp.com"]
```

---

## Common Pitfalls

### 1. Mutable Default Arguments

```python
# BAD - shared mutable default
class Bad(BaseModel):
    tags: list[str] = []   # all instances share this list!

# GOOD - use default_factory
class Good(BaseModel):
    tags: list[str] = Field(default_factory=list)
```

### 2. Forward References in Circular Models

```python
from __future__ import annotations
from pydantic import BaseModel

class Post(BaseModel):
    id: int
    author: User  # User defined below

class User(BaseModel):
    id: int
    posts: list[Post] = []

Post.model_rebuild()  # required to resolve forward reference
```

### 3. Dict vs Model Validation

```python
# model_validate expects dict or ORM object
user = UserRead.model_validate({"id": 1, "email": "a@b.com"})  # from dict
user = UserRead.model_validate(orm_user)  # from ORM (with from_attributes=True)

# model_validate_json expects JSON string (fastest)
user = UserRead.model_validate_json('{"id": 1, "email": "a@b.com"}')
```

### 4. Response Model Filtering

```python
# Use response_model to filter output fields, not return type hints
@app.get("/users/{id}", response_model=UserRead)  # filters to UserRead fields
async def get_user(id: int) -> UserInDB:  # returns full DB object
    return await db_get_user(id)  # password hash is stripped by response_model
```

### 5. Extra Fields

```python
class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")  # reject extra fields (security)
    name: str

class Flexible(BaseModel):
    model_config = ConfigDict(extra="allow")  # allow and store extra fields
    name: str
```

---

## Interactive Model Design Checklist

Use this checklist when collaborating on model design with the user:

**Entity identification:**
- [ ] What is the entity called? (domain language, singular noun)
- [ ] What are the primary identifier fields? (UUID preferred over int for external APIs)
- [ ] Which fields are required vs optional?

**Field definition per field:**
- [ ] What Python type? (str, int, float, bool, date, datetime, UUID, Enum)
- [ ] Any constraints? (min/max length, ranges, regex pattern)
- [ ] Default value or None allowed?
- [ ] Is it sensitive? (should be excluded from API responses)
- [ ] Does it map to a DB column or is it computed?

**Validation:**
- [ ] Any cross-field validation? (e.g., end > start)
- [ ] Any business rule validators? (e.g., valid country code, positive balance)
- [ ] Format constraints? (phone, email, URL, IBAN)

**API schema split:**
- [ ] What fields are in Create request? (exclude id, timestamps, computed)
- [ ] What fields are in Update request? (typically all optional)
- [ ] What fields are in Read response? (exclude passwords, internal keys)
- [ ] Are there nested relations to include? (flat vs embedded vs link)

**Examples to include in schema:**
```python
model_config = ConfigDict(
    json_schema_extra={
        "example": {
            "name": "Widget Pro",
            "price": 29.99,
            "category": "electronics"
        }
    }
)
```
