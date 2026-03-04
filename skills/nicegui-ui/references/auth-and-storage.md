# NiceGUI Authentication & Storage Reference

## Table of Contents
1. [Storage Tiers](#1-storage-tiers)
2. [Simple Password Authentication](#2-simple-password-authentication)
3. [OAuth2 — Google](#3-oauth2--google)
4. [JWT / Token-based Auth](#4-jwt--token-based-auth)
5. [Logout & Session Cleanup](#5-logout--session-cleanup)
6. [Route Protection Patterns](#6-route-protection-patterns)
7. [Storage Patterns](#7-storage-patterns)

---

## 1. Storage Tiers

NiceGUI provides three storage scopes:

| Storage | Scope | Persistence | Use for |
|---------|-------|-------------|---------|
| `app.storage.user` | Per browser session | Persisted (with `storage_secret`) | Auth state, preferences, user data |
| `app.storage.general` | Server-wide | In memory (lost on restart) | Shared counters, caches |
| `app.storage.tab` | Per browser tab | In memory (lost on refresh) | Draft state, scroll position |

```python
ui.run(
    storage_secret='change-me-in-production',  # enables user storage persistence
)
```

**Access patterns:**
```python
# Read
username = app.storage.user.get('username', 'Guest')
is_auth = app.storage.user.get('authenticated', False)

# Write
app.storage.user['authenticated'] = True
app.storage.user.update({'username': 'alice', 'role': 'admin'})

# Delete
app.storage.user.pop('token', None)
del app.storage.user['session_data']

# Bind UI directly
ui.label().bind_text_from(app.storage.user, 'username')
ui.input('Note').bind_value(app.storage.user, 'note')
```

---

## 2. Simple Password Authentication

### Middleware-based (recommended pattern)

```python
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse
from nicegui import app, ui

# Routes that don't require auth
PUBLIC_PATHS = {'/login', '/favicon.ico', '/static'}

@app.middleware('http')
async def auth_middleware(request: Request, call_next):
    # Allow public paths and NiceGUI internal paths
    path = request.url.path
    if (
        not app.storage.user.get('authenticated', False)
        and path not in PUBLIC_PATHS
        and not path.startswith('/_nicegui')
        and not path.startswith('/static')
    ):
        return RedirectResponse(f'/login?redirect_to={path}')
    return await call_next(request)


# User database (use hashed passwords in production!)
USERS = {
    'alice': 'secret123',
    'bob': 'hunter2',
}


@ui.page('/login')
def login(redirect_to: str = '/'):
    def try_login():
        if USERS.get(username.value) == password.value:
            app.storage.user.update({
                'authenticated': True,
                'username': username.value,
            })
            ui.navigate.to(redirect_to)
        else:
            error.visible = True
            password.value = ''

    with ui.card().classes('absolute-center w-96 p-8 shadow-xl'):
        ui.label('Sign In').classes('text-2xl font-bold mb-6')

        username = ui.input('Username', placeholder='Enter username').classes('w-full')
        password = ui.input('Password', placeholder='Enter password') \
            .props('type=password') \
            .classes('w-full')
        password.on('keydown.enter', try_login)

        error = ui.label('Invalid username or password') \
            .classes('text-red-500 text-sm') \
            .set_visibility(False)

        ui.button('Sign In', on_click=try_login) \
            .classes('w-full mt-4') \
            .props('color=primary size=lg')


@ui.page('/logout')
def logout():
    app.storage.user.clear()
    ui.navigate.to('/login')


@ui.page('/')
def index():
    username = app.storage.user.get('username', 'Unknown')
    ui.label(f'Welcome, {username}!').classes('text-xl')
    ui.link('Logout', '/logout')
```

---

## 3. OAuth2 — Google

```python
import httpx
from authlib.integrations.starlette_client import OAuth
from starlette.config import Config
from starlette.requests import Request

from nicegui import app, ui

# Configuration
config = Config('.env')  # or set env vars GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
oauth = OAuth(config)
oauth.register(
    name='google',
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'},
)

ALLOWED_DOMAINS = ['mycompany.com']  # restrict to your org


def _is_valid_user(user_info: dict) -> bool:
    if not user_info:
        return False
    email = user_info.get('email', '')
    if ALLOWED_DOMAINS:
        return email.split('@')[-1] in ALLOWED_DOMAINS
    return True


@ui.page('/')
async def index(request: Request):
    user_info = app.storage.user.get('user_info', {})
    if not _is_valid_user(user_info):
        return await oauth.google.authorize_redirect(
            request,
            request.url_for('auth_callback'),
        )
    # Render authenticated content
    ui.label(f'Hello, {user_info.get("name")}!')
    ui.label(user_info.get('email')).classes('text-grey-6')
    ui.button('Sign out', on_click=lambda: [app.storage.user.clear(), ui.navigate.to('/')])


@app.get('/auth/callback')
async def auth_callback(request: Request):
    token = await oauth.google.authorize_access_token(request)
    user_info = token.get('userinfo')
    if user_info and _is_valid_user(user_info):
        app.storage.user['user_info'] = dict(user_info)
    return RedirectResponse('/')


ui.run(storage_secret='change-me')
```

**Dependencies:**
```bash
pip install authlib httpx itsdangerous
```

---

## 4. JWT / Token-based Auth

For API-first or stateless auth:

```python
import jwt
from datetime import datetime, timedelta

SECRET_KEY = 'your-secret-key'
ALGORITHM = 'HS256'


def create_token(user_id: str, role: str) -> str:
    payload = {
        'sub': user_id,
        'role': role,
        'exp': datetime.utcnow() + timedelta(hours=24),
        'iat': datetime.utcnow(),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


@ui.page('/login')
def login():
    async def try_login():
        # Verify credentials...
        token = create_token(user_id='123', role='admin')
        app.storage.user['token'] = token
        ui.navigate.to('/')

    ui.button('Login', on_click=try_login)


@app.middleware('http')
async def jwt_middleware(request: Request, call_next):
    if request.url.path.startswith('/api/'):
        token = request.headers.get('Authorization', '').removeprefix('Bearer ')
        if not token:
            token = app.storage.user.get('token', '')
        payload = verify_token(token)
        if not payload:
            from starlette.responses import JSONResponse
            return JSONResponse({'error': 'Unauthorized'}, status_code=401)
        request.state.user = payload
    return await call_next(request)
```

---

## 5. Logout & Session Cleanup

```python
@ui.page('/logout')
def logout():
    # Clear all session data
    app.storage.user.clear()
    # Or selectively:
    # for key in ('authenticated', 'username', 'token', 'user_info'):
    #     app.storage.user.pop(key, None)
    ui.notify('Signed out successfully', type='positive')
    ui.navigate.to('/login')


# Logout button (in nav)
def nav_logout_button():
    async def confirm_logout():
        with ui.dialog() as d, ui.card():
            ui.label('Sign out?')
            with ui.row():
                ui.button('Cancel', on_click=d.close).props('flat')
                ui.button('Sign out', on_click=lambda: ui.navigate.to('/logout')).props('color=negative')
        await d

    ui.button('Sign out', icon='logout', on_click=confirm_logout).props('flat')
```

---

## 6. Route Protection Patterns

### Decorator-based guard
```python
from functools import wraps


def require_auth(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not app.storage.user.get('authenticated'):
            ui.navigate.to('/login')
            return
        return func(*args, **kwargs)
    return wrapper


def require_role(role: str):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            user_role = app.storage.user.get('role')
            if user_role != role:
                ui.notify('Access denied', type='negative')
                ui.navigate.to('/')
                return
            return func(*args, **kwargs)
        return wrapper
    return decorator


@ui.page('/dashboard')
@require_auth
def dashboard():
    ui.label('Dashboard')


@ui.page('/admin')
@require_auth
@require_role('admin')
def admin():
    ui.label('Admin panel')
```

### Custom sub_pages with auth
```python
from nicegui.page import sub_pages


class AuthSubPages(ui.sub_pages):
    PROTECTED_ROUTES = {'/dashboard', '/settings', '/admin'}

    def _render_page(self, match):
        if match.full_url in self.PROTECTED_ROUTES:
            if not app.storage.user.get('authenticated'):
                self._show_login(match.full_url)
                return True
        return super()._render_page(match)

    def _show_login(self, redirect_to: str):
        with ui.card().classes('absolute-center w-96 p-8'):
            ui.label('Login required').classes('text-xl font-bold mb-4')
            username = ui.input('Username').classes('w-full')
            password = ui.input('Password').props('type=password').classes('w-full')

            def try_login():
                if authenticate(username.value, password.value):
                    app.storage.user['authenticated'] = True
                    ui.navigate.to(redirect_to)
                else:
                    ui.notify('Invalid credentials', type='negative')

            ui.button('Login', on_click=try_login).classes('w-full mt-4').props('color=primary')

    def _render_404(self):
        ui.label('Page not found').classes('text-2xl font-bold text-center')
```

---

## 7. Storage Patterns

### User preferences
```python
@ui.page('/settings')
def settings():
    ui.label('Preferences').classes('text-xl font-bold mb-4')

    # These auto-persist; no save button needed
    ui.input('Display name').bind_value(app.storage.user, 'display_name').classes('w-full')
    ui.select(['en', 'de', 'fr', 'es'], label='Language').bind_value(app.storage.user, 'language')
    ui.switch('Email notifications').bind_value(app.storage.user, 'email_notifications')
    ui.switch('Dark mode').bind_value(app.storage.user, 'dark_mode').on_value_change(
        lambda e: ui.dark_mode().enable() if e.value else ui.dark_mode().disable()
    )
    ui.number('Items per page', min=5, max=100, step=5, value=20).bind_value(app.storage.user, 'page_size')
```

### Shared app counters
```python
# Initialize on startup
@app.on_startup
async def init_stats():
    if 'stats' not in app.storage.general:
        app.storage.general['stats'] = {
            'total_requests': 0,
            'active_users': 0,
        }

# Increment
app.storage.general['stats']['total_requests'] += 1

# Display
@ui.refreshable
def stats_display():
    stats = app.storage.general.get('stats', {})
    ui.label(f"Total requests: {stats.get('total_requests', 0)}")

ui.timer(5.0, stats_display.refresh)
stats_display()
```

### Per-tab draft state
```python
@ui.page('/compose')
def compose():
    # Draft saved per-tab, cleared on refresh (intentionally)
    draft = app.storage.tab

    with ui.column().classes('w-full max-w-2xl gap-4'):
        ui.label('Compose').classes('text-xl font-bold')
        subject = ui.input('Subject').bind_value(draft, 'subject').classes('w-full')
        body = ui.textarea('Message').bind_value(draft, 'body').classes('w-full')
        body.props('rows=10')

        with ui.row():
            ui.button('Send', on_click=send_email).props('color=primary')
            ui.button('Clear draft', on_click=lambda: [draft.clear(), subject.set_value(''), body.set_value('')]).props('flat')
```
