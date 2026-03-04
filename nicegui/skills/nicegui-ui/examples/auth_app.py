#!/usr/bin/env python3
"""
NiceGUI Authentication App Template
-------------------------------------
Demonstrates: middleware auth, login page, session storage, protected routes,
logout, per-user persistent storage, role-based access.
Run: python auth_app.py
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse

from nicegui import app, ui

# ─── User database (use a real DB + hashed passwords in production!) ─────────
USERS = {
    'alice': {'password': 'alice123', 'role': 'admin', 'name': 'Alice Admin'},
    'bob':   {'password': 'bob123',   'role': 'user',  'name': 'Bob User'},
}

PUBLIC_PATHS = {'/login', '/favicon.ico'}


# ─── Middleware ───────────────────────────────────────────────────────────────

@app.middleware('http')
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    if (
        not app.storage.user.get('authenticated', False)
        and path not in PUBLIC_PATHS
        and not path.startswith('/_nicegui')
    ):
        redirect_url = f'/login?redirect_to={path}'
        return RedirectResponse(redirect_url)
    return await call_next(request)


# ─── Auth helpers ─────────────────────────────────────────────────────────────

def current_user() -> dict:
    return {
        'username': app.storage.user.get('username', ''),
        'name':     app.storage.user.get('name', 'Guest'),
        'role':     app.storage.user.get('role', 'user'),
    }


def is_admin() -> bool:
    return current_user()['role'] == 'admin'


# ─── Shared frame ─────────────────────────────────────────────────────────────

def render_header():
    user = current_user()
    with ui.header(elevated=True).classes('bg-primary text-white items-center px-6 h-14 gap-3'):
        ui.label('SecureApp').classes('text-xl font-bold')
        ui.space()

        # Role badge
        role_color = 'orange' if user['role'] == 'admin' else 'blue'
        ui.badge(user['role'].upper(), color=role_color).classes('mr-2')

        ui.label(user['name']).classes('text-sm')
        ui.button('Logout', icon='logout', on_click=lambda: ui.navigate.to('/logout')).props('flat no-caps color=white')


# ─── Pages ───────────────────────────────────────────────────────────────────

@ui.page('/login')
def login(redirect_to: str = '/'):
    ui.colors(primary='#1565C0')

    with ui.column().classes('absolute-center items-center gap-0 w-full'):
        with ui.card().classes('w-96 shadow-2xl'):
            # Header
            with ui.column().classes('w-full bg-primary text-white p-6 gap-1'):
                ui.label('Welcome back').classes('text-2xl font-bold')
                ui.label('Sign in to your account').classes('text-white/70 text-sm')

            # Form
            with ui.column().classes('w-full p-6 gap-3'):
                username = ui.input(
                    'Username',
                    placeholder='Enter your username',
                ).classes('w-full')

                password = ui.input(
                    'Password',
                    placeholder='Enter your password',
                ).props('type=password clearable').classes('w-full')

                error_label = ui.label('').classes('text-red-500 text-sm -mt-1').set_visibility(False)

                def try_login():
                    uname = username.value.strip()
                    user_data = USERS.get(uname)
                    if user_data and user_data['password'] == password.value:
                        app.storage.user.update({
                            'authenticated': True,
                            'username': uname,
                            'name': user_data['name'],
                            'role': user_data['role'],
                        })
                        ui.navigate.to(redirect_to)
                    else:
                        error_label.text = 'Invalid username or password'
                        error_label.set_visibility(True)
                        password.value = ''

                password.on('keydown.enter', try_login)

                ui.button('Sign In', on_click=try_login) \
                    .classes('w-full') \
                    .props('color=primary size=lg no-caps')

                ui.label('Hint: alice/alice123 (admin) or bob/bob123 (user)') \
                    .classes('text-xs text-grey-5 text-center mt-2')


@ui.page('/logout')
def logout():
    app.storage.user.clear()
    ui.navigate.to('/login')


@ui.page('/')
def home():
    render_header()
    user = current_user()

    with ui.column().classes('w-full max-w-4xl mx-auto px-6 py-8 gap-6'):
        ui.label(f'Hello, {user["name"]}! 👋').classes('text-3xl font-bold')
        ui.label('You are successfully authenticated.').classes('text-grey-6')

        # Navigation cards
        with ui.grid(columns=2).classes('w-full gap-4'):
            with ui.card().classes('p-5 cursor-pointer hover:shadow-lg transition-shadow') \
                    .on('click', lambda: ui.navigate.to('/profile')):
                with ui.row().classes('items-center gap-3'):
                    ui.icon('person', size='2rem', color='primary')
                    with ui.column():
                        ui.label('My Profile').classes('font-semibold')
                        ui.label('View and edit your profile').classes('text-sm text-grey-6')

            with ui.card().classes('p-5 cursor-pointer hover:shadow-lg transition-shadow') \
                    .on('click', lambda: ui.navigate.to('/settings')):
                with ui.row().classes('items-center gap-3'):
                    ui.icon('settings', size='2rem', color='secondary')
                    with ui.column():
                        ui.label('Settings').classes('font-semibold')
                        ui.label('Configure your preferences').classes('text-sm text-grey-6')

            if is_admin():
                with ui.card().classes('p-5 cursor-pointer hover:shadow-lg transition-shadow bg-orange-50') \
                        .on('click', lambda: ui.navigate.to('/admin')):
                    with ui.row().classes('items-center gap-3'):
                        ui.icon('admin_panel_settings', size='2rem', color='orange')
                        with ui.column():
                            ui.label('Admin Panel').classes('font-semibold')
                            ui.label('Admin-only access').classes('text-sm text-grey-6')


@ui.page('/profile')
def profile():
    render_header()
    user = current_user()

    with ui.column().classes('w-full max-w-2xl mx-auto px-6 py-8 gap-6'):
        ui.label('My Profile').classes('text-3xl font-bold')

        with ui.card().classes('w-full p-6'):
            with ui.row().classes('items-center gap-4 mb-6'):
                ui.avatar(user['name'][0].upper(), size='4rem', color='primary', text_color='white')
                with ui.column():
                    ui.label(user['name']).classes('text-xl font-semibold')
                    ui.label(f"@{user['username']}").classes('text-grey-6')
                    ui.badge(user['role'], color='blue').classes('mt-1')

            ui.separator()

            with ui.column().classes('w-full gap-3 mt-4'):
                ui.label('Account Details').classes('font-semibold text-grey-8')
                with ui.row().classes('gap-6 text-sm'):
                    with ui.column():
                        ui.label('Username').classes('text-grey-5 uppercase text-xs tracking-wider')
                        ui.label(user['username']).classes('font-medium')
                    with ui.column():
                        ui.label('Role').classes('text-grey-5 uppercase text-xs tracking-wider')
                        ui.label(user['role'].title()).classes('font-medium')

        with ui.card().classes('w-full p-6'):
            ui.label('Personal Notes').classes('font-semibold mb-3')
            ui.label('Your notes are saved automatically.').classes('text-sm text-grey-6 mb-2')
            ui.textarea(placeholder='Write your notes here...') \
                .bind_value(app.storage.user, 'notes') \
                .classes('w-full') \
                .props('rows=5')


@ui.page('/settings')
def settings():
    render_header()

    with ui.column().classes('w-full max-w-2xl mx-auto px-6 py-8 gap-6'):
        ui.label('Settings').classes('text-3xl font-bold')

        with ui.card().classes('w-full p-6'):
            ui.label('Preferences').classes('font-semibold mb-4')
            dark = ui.dark_mode()

            with ui.column().classes('gap-3'):
                ui.switch('Dark mode').bind_value(app.storage.user, 'dark_mode').on_value_change(
                    lambda e: dark.enable() if e.value else dark.disable()
                )
                ui.switch('Email notifications', value=True).bind_value(app.storage.user, 'email_notifs')
                ui.select(
                    ['English', 'German', 'French', 'Spanish'],
                    label='Language',
                    value='English',
                ).bind_value(app.storage.user, 'language').classes('w-48')


@ui.page('/admin')
def admin():
    # Extra check in page (middleware handles redirect, this is defense-in-depth)
    if not is_admin():
        ui.label('Access Denied').classes('text-2xl text-red-500 absolute-center')
        return

    render_header()
    with ui.column().classes('w-full max-w-4xl mx-auto px-6 py-8 gap-6'):
        with ui.row().classes('items-center gap-3'):
            ui.label('Admin Panel').classes('text-3xl font-bold')
            ui.badge('ADMIN', color='orange')

        with ui.card().classes('w-full p-6'):
            ui.label('User Management').classes('font-semibold mb-4')

            columns = [
                {'name': 'username', 'label': 'Username', 'field': 'username', 'sortable': True},
                {'name': 'name',     'label': 'Name',     'field': 'name'},
                {'name': 'role',     'label': 'Role',     'field': 'role',     'sortable': True},
            ]
            rows = [
                {'username': uname, 'name': data['name'], 'role': data['role']}
                for uname, data in USERS.items()
            ]
            ui.table(columns=columns, rows=rows, row_key='username').classes('w-full')


# ─── Run ─────────────────────────────────────────────────────────────────────

ui.run(
    title='Auth App',
    port=8081,
    storage_secret='change-me-in-production-please',
    reload=True,
)
