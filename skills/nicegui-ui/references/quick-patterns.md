# NiceGUI — Core Code Patterns

> Always-available snippets. Load this file whenever coding NiceGUI.

## Reusable app frame

```python
from contextlib import contextmanager
from nicegui import ui, app

@contextmanager
def app_frame(title: str = '', active: str = '/'):
    with ui.header(elevated=True).classes('bg-primary text-white items-center px-6 h-14 gap-3'):
        ui.button(icon='menu', on_click=lambda: drawer.toggle()).props('flat round color=white')
        ui.label('AppName').classes('text-xl font-bold flex-1')
        ui.label(app.storage.user.get('username', '')).classes('text-sm opacity-70')
    with ui.left_drawer(value=False).classes('bg-white border-r pt-4') as drawer:
        _render_nav(active)
    with ui.column().classes('w-full max-w-6xl mx-auto px-6 py-8 gap-6'):
        if title:
            ui.label(title).classes('text-3xl font-bold')
        yield
```

## @ui.refreshable list

```python
items: list[dict] = []

@ui.refreshable
def item_list():
    for item in items:
        with ui.card().classes('w-full p-4'):
            ui.label(item['name'])

def add_item(name: str):
    items.append({'name': name})
    item_list.refresh()

item_list()
```

## Async page load (spinner → data)

```python
@ui.page('/')
async def index():
    spinner = ui.spinner(size='xl').classes('absolute-center')
    await ui.context.client.connected()
    data = await fetch_all_data()
    spinner.delete()
    render_page(data)
```

## Awaitable confirm dialog

```python
async def confirm_delete(name: str) -> bool:
    with ui.dialog() as d, ui.card().classes('w-80 p-6'):
        ui.label(f'Delete "{name}"?').classes('text-lg font-semibold')
        ui.label('This cannot be undone.').classes('text-sm text-grey-6 mt-1')
        with ui.row().classes('justify-end gap-2 mt-6'):
            ui.button('Cancel', on_click=lambda: d.submit(False)).props('flat no-caps')
            ui.button('Delete', on_click=lambda: d.submit(True)).props('color=negative no-caps')
    return await d
```

## Standard color palette

```python
ui.colors(
    primary='#1565C0',
    secondary='#00897B',
    accent='#F57C00',
    positive='#2E7D32',
    negative='#C62828',
    info='#0277BD',
    warning='#E65100',
)
```

## Canonical project structure

```
project/
├── main.py                  # ui.run() entry point
├── components/              # Reusable UI components
│   ├── __init__.py
│   ├── frame.py             # app_frame context manager
│   └── *.py
├── pages/                   # Page content functions
│   ├── __init__.py
│   └── *.py
├── routers/                 # APIRouter modules
├── static/                  # CSS, images, fonts
├── .env                     # STORAGE_SECRET, API keys
├── Dockerfile
└── docker-compose.yml
```
