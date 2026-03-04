#!/usr/bin/env python3
"""
Basic NiceGUI App Template
--------------------------
Demonstrates: header/drawer, tabs, cards, inputs, dialogs, notify, timer.
Run: python basic_app.py
"""
from contextlib import contextmanager

from nicegui import app, ui


# ─── Shared navigation ───────────────────────────────────────────────────────

NAV_ITEMS = [
    ('/', 'home', 'Home'),
    ('/settings', 'settings', 'Settings'),
]


@contextmanager
def page_frame(title: str = '', active: str = '/'):
    """Reusable page shell with header and left drawer."""
    with ui.header(elevated=True).classes('bg-primary text-white items-center px-6 h-14 gap-3'):
        ui.button(icon='menu', on_click=lambda: drawer.toggle()).props('flat round color=white')
        ui.label('MyApp').classes('text-xl font-bold')
        if title:
            ui.label(f'/ {title}').classes('text-white/60 text-sm')
        ui.space()
        ui.button(icon='account_circle').props('flat round color=white')

    with ui.left_drawer(value=False).classes('bg-white border-r pt-4') as drawer:
        for route, icon, label in NAV_ITEMS:
            is_active = active == route
            with ui.item(on_click=lambda r=route: ui.navigate.to(r)).classes(
                'rounded-lg mx-2 ' + ('bg-primary/10 text-primary' if is_active else 'hover:bg-grey-1')
            ):
                with ui.item_section().props('avatar'):
                    ui.icon(icon, color='primary' if is_active else 'grey-7')
                with ui.item_section():
                    ui.item_label(label)

    with ui.column().classes('w-full max-w-5xl mx-auto px-6 py-8 gap-6'):
        if title:
            ui.label(title).classes('text-3xl font-bold text-grey-9')
        yield


# ─── Pages ───────────────────────────────────────────────────────────────────

@ui.page('/')
def home():
    with page_frame('Dashboard', active='/'):

        # Metric cards
        with ui.grid(columns=3).classes('w-full gap-4'):
            for label, value, change, color in [
                ('Total Users', '1,234', '+12%', 'text-blue-600'),
                ('Revenue', '$45,231', '+8.1%', 'text-green-600'),
                ('Active Tasks', '23', '-2%', 'text-orange-600'),
            ]:
                with ui.card().classes('p-5'):
                    ui.label(label).classes('text-sm text-grey-6 uppercase tracking-wider')
                    ui.label(value).classes(f'text-3xl font-bold mt-1 {color}')
                    ui.label(change).classes('text-sm text-grey-5 mt-1')

        # Tabs section
        with ui.card().classes('w-full'):
            with ui.tabs().classes('w-full') as tabs:
                ui.tab('overview', label='Overview', icon='dashboard')
                ui.tab('activity', label='Activity', icon='timeline')

            with ui.tab_panels(tabs, value='overview').classes('w-full p-4'):
                with ui.tab_panel('overview'):
                    overview_panel()
                with ui.tab_panel('activity'):
                    activity_panel()

        # Dialog example
        demo_section()


def overview_panel():
    ui.label('Recent Items').classes('text-lg font-semibold mb-3')
    items = [
        {'name': 'Project Alpha', 'status': 'active', 'progress': 0.75},
        {'name': 'Project Beta', 'status': 'pending', 'progress': 0.30},
        {'name': 'Project Gamma', 'status': 'done', 'progress': 1.0},
    ]
    status_colors = {'active': 'green', 'pending': 'orange', 'done': 'blue'}

    for item in items:
        with ui.row().classes('w-full items-center gap-4 py-2 border-b border-grey-2 last:border-0'):
            ui.label(item['name']).classes('flex-1 font-medium')
            ui.badge(item['status'], color=status_colors[item['status']])
            ui.linear_progress(value=item['progress']).classes('w-32')
            ui.label(f"{int(item['progress']*100)}%").classes('text-sm text-grey-6 w-10 text-right')


def activity_panel():
    ui.label('Recent Activity').classes('text-lg font-semibold mb-3')
    events = [
        ('Alice created Project Alpha', '2 hours ago', 'add_circle', 'text-green-600'),
        ('Bob updated status to Active', '4 hours ago', 'edit', 'text-blue-600'),
        ('Charlie commented on task', '6 hours ago', 'chat', 'text-purple-600'),
        ('System completed backup', '1 day ago', 'check_circle', 'text-grey-5'),
    ]
    for text, time, icon, color in events:
        with ui.row().classes('w-full items-start gap-3 py-2'):
            ui.icon(icon).classes(f'{color} text-xl mt-0.5')
            with ui.column().classes('flex-1 gap-0'):
                ui.label(text).classes('text-sm')
                ui.label(time).classes('text-xs text-grey-5')


def demo_section():
    with ui.card().classes('w-full p-5'):
        ui.label('Interactive Demo').classes('text-lg font-semibold mb-3')

        # Timer demo
        counter = {'n': 0}
        count_label = ui.label('Counter: 0').classes('text-2xl font-bold text-primary')
        timer = ui.timer(1.0, lambda: [counter.update(n=counter['n'] + 1), count_label.set_text(f"Counter: {counter['n']}")], active=False)

        with ui.row().classes('gap-2 mb-4'):
            ui.button('Start Timer', on_click=timer.activate).props('color=primary outline')
            ui.button('Stop Timer', on_click=timer.deactivate).props('color=grey outline')
            ui.button('Reset', on_click=lambda: [counter.update(n=0), count_label.set_text('Counter: 0')]).props('flat')

        ui.separator().classes('my-3')

        # Dialog demo
        async def open_dialog():
            with ui.dialog() as dialog, ui.card().classes('w-80 p-6'):
                ui.label('Confirmation').classes('text-lg font-semibold')
                ui.label('Are you sure you want to proceed?').classes('text-grey-6 mt-1')
                with ui.row().classes('w-full justify-end gap-2 mt-4'):
                    ui.button('Cancel', on_click=lambda: dialog.submit(False)).props('flat')
                    ui.button('Confirm', on_click=lambda: dialog.submit(True)).props('color=primary')
            result = await dialog
            ui.notify(
                'Confirmed!' if result else 'Cancelled',
                type='positive' if result else 'info',
            )

        ui.button('Open Dialog', icon='open_in_new', on_click=open_dialog).props('color=secondary')


@ui.page('/settings')
def settings():
    with page_frame('Settings', active='/settings'):
        with ui.card().classes('w-full max-w-xl p-6'):
            ui.label('User Preferences').classes('text-xl font-semibold mb-4')

            ui.input('Display name', value='Alice').classes('w-full').bind_value(app.storage.user, 'display_name')
            ui.input('Email').props('type=email').classes('w-full')
            ui.separator().classes('my-3')

            ui.label('Notifications').classes('font-medium mb-2')
            ui.switch('Email notifications', value=True).bind_value(app.storage.user, 'email_notifications')
            ui.switch('Push notifications').bind_value(app.storage.user, 'push_notifications')
            ui.separator().classes('my-3')

            dark = ui.dark_mode()
            ui.switch('Dark mode').bind_value(app.storage.user, 'dark_mode').on_value_change(
                lambda e: dark.enable() if e.value else dark.disable()
            )

            with ui.row().classes('w-full justify-end mt-6'):
                ui.button('Save', icon='save', on_click=lambda: ui.notify('Saved!', type='positive')).props('color=primary')


# ─── Run ─────────────────────────────────────────────────────────────────────

ui.run(
    title='Basic NiceGUI App',
    port=8080,
    storage_secret='dev-secret-change-in-prod',
    reload=True,
)
