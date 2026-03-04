#!/usr/bin/env python3
"""
NiceGUI Real-Time Chat App Template
--------------------------------------
Demonstrates: multi-client Event[T], @ui.refreshable, chat_message,
per-user storage, online user list, client lifecycle, message history.
Run: python chat_app.py
"""
import uuid
from datetime import datetime

from nicegui import app, ui
from nicegui.events import Event

# ─── Shared state (server-side, all clients) ──────────────────────────────────

messages: list[dict] = []           # chat history
online_users: dict[str, str] = {}   # client_id → username

# Typed broadcast events
new_message  = Event[dict]()        # emitted when a message is sent
users_changed = Event[dict]()       # emitted when online users change

MAX_MESSAGES = 200


# ─── Color palette for user avatars ──────────────────────────────────────────

USER_COLORS = [
    'primary', 'secondary', 'accent',
    'positive', 'negative', 'info', 'warning',
]

def user_color(username: str) -> str:
    return USER_COLORS[hash(username) % len(USER_COLORS)]


# ─── Helper ───────────────────────────────────────────────────────────────────

def format_time(dt: datetime) -> str:
    now = datetime.now()
    if dt.date() == now.date():
        return dt.strftime('%H:%M')
    return dt.strftime('%b %d, %H:%M')


# ─── Login page ───────────────────────────────────────────────────────────────

@ui.page('/login')
def login_page():
    ui.colors(primary='#6366F1')

    with ui.column().classes('absolute-center items-center gap-4 w-full'):
        ui.icon('chat', size='4rem', color='primary')
        ui.label('NiceGUI Chat').classes('text-3xl font-bold text-primary')
        ui.label('Enter your name to join the chat').classes('text-grey-6')

        with ui.card().classes('w-80 p-6 shadow-xl'):
            username_inp = ui.input(
                'Your name',
                placeholder='e.g. Alice',
            ).classes('w-full').props('autofocus')

            error_lbl = ui.label('').classes('text-red-500 text-sm').set_visibility(False)

            def join():
                name = username_inp.value.strip()
                if not name:
                    error_lbl.text = 'Please enter your name'
                    error_lbl.set_visibility(True)
                    return
                if len(name) > 30:
                    error_lbl.text = 'Name too long (max 30 chars)'
                    error_lbl.set_visibility(True)
                    return
                app.storage.user['username'] = name
                ui.navigate.to('/')

            username_inp.on('keydown.enter', join)
            ui.button('Join Chat', icon='login', on_click=join) \
                .classes('w-full') \
                .props('color=primary no-caps size=lg')


# ─── Main chat page ───────────────────────────────────────────────────────────

@ui.page('/')
async def chat_page():
    username = app.storage.user.get('username')
    if not username:
        ui.navigate.to('/login')
        return

    client_id = str(uuid.uuid4())
    own_color = user_color(username)

    # Register this user as online
    online_users[client_id] = username
    users_changed.emit(dict(online_users))

    ui.colors(primary='#6366F1')

    # ── Layout ────────────────────────────────────────────────────────────────

    with ui.header(elevated=True).classes('bg-primary text-white items-center px-4 h-14 gap-3'):
        ui.icon('chat').classes('text-xl')
        ui.label('NiceGUI Chat').classes('text-xl font-bold flex-1')
        ui.chip(
            f'Online: {len(online_users)}',
            icon='people',
        ).props('color=white text-color=primary').mark('online-count')
        ui.button(
            'Leave',
            icon='logout',
            on_click=lambda: ui.navigate.to('/login'),
        ).props('flat no-caps color=white')

    with ui.splitter(value=75).classes('flex-1 h-full') as splitter:

        # ── Message panel (left) ──────────────────────────────────────────────
        with splitter.before:
            with ui.column().classes('w-full h-full flex flex-col'):

                # Message list
                scroll = ui.scroll_area().classes('flex-1 w-full px-4 py-2')
                with scroll:
                    messages_container = ui.column().classes('w-full gap-2')

                with messages_container:
                    _render_all_messages(messages, own_id=client_id)

                # System message: user joined
                _add_system_message(f'{username} joined the chat')

                # Input bar
                with ui.row().classes('w-full items-center gap-2 px-4 py-3 border-t border-grey-2 bg-white'):
                    msg_input = ui.input(
                        placeholder=f'Message as {username}...',
                    ).classes('flex-1').props('outlined dense autofocus')

                    send_btn = ui.button(icon='send').props('color=primary round')

                    def send_message():
                        text = msg_input.value.strip()
                        if not text:
                            return
                        msg = {
                            'id':        str(uuid.uuid4()),
                            'sender_id': client_id,
                            'sender':    username,
                            'text':      text,
                            'time':      datetime.now(),
                            'type':      'message',
                        }
                        messages.append(msg)
                        if len(messages) > MAX_MESSAGES:
                            messages.pop(0)
                        new_message.emit(msg)
                        msg_input.value = ''

                    msg_input.on('keydown.enter', send_message)
                    send_btn.on('click', send_message)

        # ── Sidebar: online users (right) ─────────────────────────────────────
        with splitter.after:
            with ui.column().classes('w-full h-full bg-grey-1 border-l border-grey-2'):
                ui.label('Online').classes('text-xs uppercase tracking-wider text-grey-5 px-4 pt-4 pb-2')

                online_list = ui.column().classes('w-full px-2 gap-1')
                with online_list:
                    _render_online_users(dict(online_users), client_id)

    # ── Event subscriptions (per-client) ──────────────────────────────────────

    @new_message.subscribe
    def on_new_message(msg: dict):
        _append_message(messages_container, msg, own_id=client_id)
        # Scroll to bottom
        ui.run_javascript(f'document.querySelector(".q-scrollarea__container").scrollTop = 999999')

    @users_changed.subscribe
    def on_users_changed(users: dict):
        # Update online count badge
        count_chip = ui.query('[data-mark="online-count"]')
        # Rebuild online list
        online_list.clear()
        with online_list:
            _render_online_users(users, client_id)

    # ── Cleanup on disconnect ─────────────────────────────────────────────────

    await ui.context.client.connected()

    await ui.context.client.disconnected()

    online_users.pop(client_id, None)
    users_changed.emit(dict(online_users))
    _add_system_message(f'{username} left the chat')


# ─── Rendering helpers ────────────────────────────────────────────────────────

def _render_all_messages(msgs: list[dict], own_id: str):
    for msg in msgs:
        _append_message(None, msg, own_id=own_id)


def _append_message(container, msg: dict, own_id: str):
    ctx = container if container else ui.column()
    with ctx:
        if msg['type'] == 'system':
            ui.label(msg['text']).classes('text-xs text-grey-4 text-center italic py-1')
        else:
            is_own = msg['sender_id'] == own_id
            color = user_color(msg['sender'])
            ui.chat_message(
                text=msg['text'],
                name=msg['sender'] if not is_own else 'You',
                stamp=format_time(msg['time']),
                sent=is_own,
                avatar=f'https://ui-avatars.com/api/?name={msg["sender"]}&background=random&size=32',
            ).props(f'bg-color={color if not is_own else "primary"}')


def _render_online_users(users: dict, own_id: str):
    for cid, uname in users.items():
        color = user_color(uname)
        with ui.row().classes('items-center gap-2 px-2 py-1.5 rounded hover:bg-grey-2'):
            ui.avatar(uname[0].upper(), size='1.75rem', color=color, text_color='white')
            with ui.column().classes('gap-0'):
                ui.label(uname + (' (you)' if cid == own_id else '')).classes('text-sm font-medium')
            ui.icon('circle').classes('text-green-400 text-xs ml-auto')


def _add_system_message(text: str):
    msg = {
        'id':        str(uuid.uuid4()),
        'sender_id': 'system',
        'sender':    'System',
        'text':      text,
        'time':      datetime.now(),
        'type':      'system',
    }
    messages.append(msg)
    new_message.emit(msg)


# ─── Run ─────────────────────────────────────────────────────────────────────

ui.run(
    title='NiceGUI Chat',
    port=8083,
    storage_secret='chat-app-secret',
    reload=True,
)
