# NiceGUI Data Binding & Reactivity Reference

## Table of Contents
1. [Bind Methods Overview](#1-bind-methods-overview)
2. [bind_value — Two-Way Binding](#2-bind_value--two-way-binding)
3. [One-Way Bindings](#3-one-way-bindings)
4. [Binding to Storage](#4-binding-to-storage)
5. [@ui.refreshable — Dynamic Rebuild](#5-uirefreshable--dynamic-rebuild)
6. [Manual Updates — clear() + rebuild](#6-manual-updates--clear--rebuild)
7. [BindableProperty — Custom Bindable Attributes](#7-bindableproperty--custom-bindable-attributes)
8. [Reactivity Patterns](#8-reactivity-patterns)

---

## 1. Bind Methods Overview

| Method | Direction | Description |
|--------|-----------|-------------|
| `bind_value(obj, attr)` | ↔ Two-way | Sync element value with object attribute |
| `bind_value_from(obj, attr)` | → One-way | Object → element only |
| `bind_value_to(obj, attr)` | ← One-way | Element → object only |
| `bind_text(obj, attr)` | ↔ Two-way | Sync element text |
| `bind_text_from(obj, attr)` | → One-way | Object → element text |
| `bind_visibility(obj, attr)` | ↔ Two-way | Sync visibility |
| `bind_visibility_from(obj, attr)` | → One-way | Object → element visibility |
| `bind_enabled_from(obj, attr)` | → One-way | Object → element enabled state |

All bind methods accept a `backward=` transform function applied when reading from the object, and `forward=` when writing to the object.

---

## 2. bind_value — Two-Way Binding

### Bind to a plain object attribute
```python
class Settings:
    theme: str = 'light'
    font_size: int = 14
    notifications: bool = True

settings = Settings()

ui.select(['light', 'dark'], label='Theme').bind_value(settings, 'theme')
ui.number('Font size', min=10, max=24).bind_value(settings, 'font_size')
ui.checkbox('Notifications').bind_value(settings, 'notifications')
```

### Bind to a dict key
```python
state = {'name': '', 'email': '', 'active': True}

ui.input('Name').bind_value(state, 'name')
ui.input('Email').bind_value(state, 'email')
ui.switch('Active').bind_value(state, 'active')
```

### With value transformation
```python
# backward: object value → displayed value
# forward: displayed value → object value
temp_c = {'value': 0.0}

ui.number('Temperature (°F)').bind_value(
    temp_c, 'value',
    forward=lambda f: (f - 32) * 5 / 9,   # °F → °C for storage
    backward=lambda c: c * 9 / 5 + 32,    # °C → °F for display
)
```

### Bind elements to each other
```python
# slider controls label
slider = ui.slider(min=0, max=100, value=50)
label = ui.label()
label.bind_text_from(slider, 'value', backward=lambda v: f'{v:.0f}%')
```

---

## 3. One-Way Bindings

### bind_value_from — display a computed/external value
```python
import psutil

cpu_label = ui.label()
cpu_label.bind_text_from(
    psutil, 'cpu_percent',
    backward=lambda v: f'CPU: {v}%'
)

# Or poll and update manually
def update():
    cpu_label.text = f'CPU: {psutil.cpu_percent()}%'
ui.timer(2.0, update)
```

### bind_visibility_from — conditional display
```python
details = {'show': False}

toggle = ui.checkbox('Show details').bind_value(details, 'show')
panel = ui.column()
panel.bind_visibility_from(details, 'show')

# Invert with backward
save_btn.bind_visibility_from(form, 'dirty', backward=lambda v: bool(v))
spinner.bind_visibility_from(state, 'loading')
empty_state.bind_visibility_from(items, '__len__', backward=lambda v: v == 0)
```

### bind_enabled_from — enable/disable control
```python
has_selection = {'value': False}

table = ui.table(columns=cols, rows=rows, selection='multiple')
delete_btn = ui.button('Delete selected').props('color=negative')
delete_btn.bind_enabled_from(table, 'selected', backward=lambda v: bool(v))
```

---

## 4. Binding to Storage

`app.storage.user` / `.general` / `.tab` are dict-like objects that work with bind:

```python
from nicegui import app, ui

@ui.page('/settings')
def settings():
    ui.label('User Settings').classes('text-xl font-bold')

    # Inputs bound to persistent user storage
    ui.input('Display name').bind_value(app.storage.user, 'display_name')
    ui.input('Email').props('type=email').bind_value(app.storage.user, 'email')
    ui.switch('Email notifications').bind_value(app.storage.user, 'email_notifications')
    ui.select(['en', 'de', 'fr'], label='Language').bind_value(app.storage.user, 'lang')

    # All changes persist immediately — no Save button needed
    ui.label('Changes are saved automatically').classes('text-sm text-grey-6 mt-4')
```

**Storage tiers:**
- `app.storage.user` — per browser session (persisted to file if `storage_secret` set)
- `app.storage.general` — shared across all users (server-wide)
- `app.storage.tab` — per browser tab (lost on refresh)

```python
# Requires storage_secret to persist between restarts
ui.run(storage_secret='change-me-in-production')
```

---

## 5. @ui.refreshable — Dynamic Rebuild

Mark a function with `@ui.refreshable`. Call `.refresh()` to tear down and rebuild its content.

### Basic usage
```python
from nicegui import ui

todos: list[dict] = []

@ui.refreshable
def todo_list():
    if not todos:
        ui.label('No items yet').classes('text-grey-5 italic')
    for todo in todos:
        with ui.row().classes('items-center gap-2'):
            ui.checkbox(value=todo['done']).bind_value(todo, 'done')
            ui.label(todo['text']).classes(
                'line-through text-grey-5' if todo['done'] else ''
            )
            ui.button(icon='delete', on_click=lambda t=todo: remove(t)).props('flat round size=sm color=negative')


def add(text: str):
    todos.append({'text': text, 'done': False})
    todo_list.refresh()

def remove(todo: dict):
    todos.remove(todo)
    todo_list.refresh()


with ui.card().classes('w-96'):
    todo_list()  # initial render
    with ui.row().classes('w-full items-center gap-2 mt-2'):
        new_item = ui.input(placeholder='New todo').classes('flex-1')
        ui.button(icon='add', on_click=lambda: [add(new_item.value), setattr(new_item, 'value', '')]).props('flat round color=primary')
```

### With async data
```python
@ui.refreshable
async def user_list():
    spinner = ui.spinner()
    users = await fetch_users_from_db()
    spinner.delete()
    for user in users:
        with ui.card().classes('w-full p-3'):
            ui.label(user['name']).classes('font-medium')
            ui.label(user['email']).classes('text-sm text-grey-6')

# Initial render
user_list()

# Refresh after edit
async def save_user(user):
    await update_user_in_db(user)
    await user_list.refresh()
```

### With arguments
```python
@ui.refreshable
def project_card(project_id: str):
    project = get_project(project_id)
    ui.label(project['name']).classes('font-bold')
    ui.label(project['status'])

# Render multiple
for pid in project_ids:
    project_card(pid)

# Refresh specific one
project_card.refresh(specific_project_id)  # only if supported
```

### Best practices
- Keep `@ui.refreshable` functions focused — they rebuild entirely on refresh
- Use for lists, dashboards, dynamic forms — anything where data changes
- Avoid deeply nested `@ui.refreshable` as child refreshes don't cascade
- For surgical updates (single label text), prefer `element.text = new_value`

---

## 6. Manual Updates — clear() + rebuild

For containers, clear and rebuild children directly:

```python
container = ui.column().classes('w-full gap-2')

def refresh_items(items: list):
    container.clear()
    with container:
        for item in items:
            with ui.card().classes('w-full p-3'):
                ui.label(item['name'])
                ui.label(item['description']).classes('text-sm text-grey-6')
```

### Surgical updates (preferred for performance)
```python
# Don't rebuild — just update the element
label.text = new_text
label.set_text(new_text)
label.set_content(html_string)

element.visible = True/False
element.enabled = True/False

# Update classes
label.classes('text-green-600', remove='text-red-600')

# Remove single element
element.delete()

# Move element to new container
element.move(new_container)
```

---

## 7. BindableProperty — Custom Bindable Attributes

Add bindable properties to custom elements:

```python
from nicegui import ui
from nicegui.binding import BindableProperty

class StatusCard(ui.card):
    status = BindableProperty(
        on_change=lambda sender, value: sender._apply_status(value)
    )

    def __init__(self, label: str, initial_status: str = 'unknown'):
        super().__init__()
        self.status = initial_status
        with self:
            self._label = ui.label(label).classes('font-medium')
            self._badge = ui.badge(initial_status)

    def _apply_status(self, value: str):
        self._badge.text = value
        colors = {
            'online': 'green',
            'offline': 'red',
            'unknown': 'grey',
            'degraded': 'orange',
        }
        self._badge.props(f'color={colors.get(value, "grey")}')


# Usage with binding
server_state = {'status': 'unknown'}

card = StatusCard('Main Server')
card.bind_value_from(server_state, 'status')  # auto-updates when dict changes

# Trigger update
server_state['status'] = 'online'   # card auto-refreshes
```

---

## 8. Reactivity Patterns

### Form state tracking
```python
class FormState:
    def __init__(self, initial: dict):
        self._initial = initial.copy()
        self.data = initial.copy()
        self.dirty: bool = False
        self.errors: dict = {}

    def update(self, key: str, value):
        self.data[key] = value
        self.dirty = self.data != self._initial

    def reset(self):
        self.data = self._initial.copy()
        self.dirty = False
        self.errors = {}


form = FormState({'name': 'Alice', 'email': 'alice@example.com'})

name_input = ui.input('Name', value=form.data['name'])
name_input.on_value_change(lambda e: form.update('name', e.value))

email_input = ui.input('Email', value=form.data['email'])
email_input.on_value_change(lambda e: form.update('email', e.value))

save_btn = ui.button('Save', on_click=save)
save_btn.bind_enabled_from(form, 'dirty')

discard_btn = ui.button('Discard').props('flat')
discard_btn.bind_visibility_from(form, 'dirty')
discard_btn.on_click(lambda: [form.reset(), name_input.set_value(form.data['name']), email_input.set_value(form.data['email'])])
```

### Reactive counter / statistics
```python
from dataclasses import dataclass, field

@dataclass
class AppStats:
    requests: int = 0
    errors: int = 0
    active_users: int = 0

stats = AppStats()

@ui.refreshable
def stats_bar():
    with ui.row().classes('gap-6'):
        for label, val, color in [
            ('Requests', stats.requests, 'text-blue-600'),
            ('Errors', stats.errors, 'text-red-600'),
            ('Active Users', stats.active_users, 'text-green-600'),
        ]:
            with ui.column().classes('items-center'):
                ui.label(str(val)).classes(f'text-3xl font-bold {color}')
                ui.label(label).classes('text-xs text-grey-6 uppercase')

stats_bar()
ui.timer(5.0, stats_bar.refresh)
```

### Search / filter pattern
```python
all_items = [{'name': 'Apple', 'category': 'fruit'}, ...]
filter_state = {'query': '', 'category': 'all'}

@ui.refreshable
def filtered_list():
    q = filter_state['query'].lower()
    cat = filter_state['category']
    shown = [
        i for i in all_items
        if (not q or q in i['name'].lower()) and (cat == 'all' or i['category'] == cat)
    ]

    if not shown:
        ui.label('No results').classes('text-grey-5 italic text-center py-8')
        return

    for item in shown:
        with ui.card().classes('w-full p-3'):
            ui.label(item['name'])

def update_query(e):
    filter_state['query'] = e.value
    filtered_list.refresh()

def update_category(e):
    filter_state['category'] = e.value
    filtered_list.refresh()

with ui.row().classes('w-full gap-4 mb-4'):
    ui.input(placeholder='Search...', on_change=update_query).classes('flex-1').props('clearable')
    ui.select(['all', 'fruit', 'vegetable'], value='all', on_change=update_category).classes('w-40')

filtered_list()
```
