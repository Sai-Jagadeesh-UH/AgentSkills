# NiceGUI Layouts & Styling Reference

## Table of Contents
1. [Tailwind CSS in NiceGUI](#1-tailwind-css-in-nicegui)
2. [Common Layout Patterns](#2-common-layout-patterns)
3. [Theming with ui.colors()](#3-theming-with-uicolors)
4. [Dark Mode](#4-dark-mode)
5. [Props System (Quasar)](#5-props-system-quasar)
6. [Inline Styles](#6-inline-styles)
7. [CSS Injection](#7-css-injection)
8. [Responsive Design](#8-responsive-design)
9. [Reusable Frames with Context Managers](#9-reusable-frames-with-context-managers)

---

## 1. Tailwind CSS in NiceGUI

NiceGUI includes Tailwind CSS. Apply classes with `.classes()`:

```python
element.classes('text-2xl font-bold text-primary')
element.classes('w-full max-w-2xl mx-auto')
element.classes('bg-blue-100 rounded-lg p-4 shadow')
```

**Toggle classes dynamically:**
```python
# Add classes
btn.classes('ring-2 ring-primary')

# Remove specific classes
btn.classes(remove='ring-2 ring-primary')

# Replace all classes
btn.classes(replace='bg-red-500 text-white px-4 py-2')

# Conditional (Python logic)
label.classes('text-green-600' if value > 0 else 'text-red-600')
```

### Typography
```python
ui.label('H1 Title').classes('text-4xl font-extrabold')
ui.label('H2 Section').classes('text-2xl font-bold')
ui.label('H3 Sub').classes('text-xl font-semibold')
ui.label('Body').classes('text-base text-grey-8')
ui.label('Caption').classes('text-sm text-grey-6')
ui.label('Overline').classes('text-xs uppercase tracking-wider text-grey-5')
ui.label('Mono code').classes('font-mono text-sm bg-grey-2 px-1 rounded')
```

### Spacing
```python
# Padding
.classes('p-4')       # all sides
.classes('px-6 py-3') # horizontal/vertical
.classes('pt-2 pb-8') # top/bottom

# Margin
.classes('m-4 mx-auto mt-8')

# Gap (flex/grid children spacing)
.classes('gap-4 gap-x-6 gap-y-2')
```

### Width & Height
```python
.classes('w-full')     # 100%
.classes('w-96')       # 24rem fixed
.classes('w-1/2')      # 50%
.classes('max-w-2xl')  # max-width: 42rem
.classes('min-w-0')    # min-width: 0 (prevents flex overflow)

.classes('h-full h-screen h-64')  # various heights
.classes('min-h-screen')          # full viewport height
```

### Colors
```python
# Text color
.classes('text-primary text-secondary text-grey-6')
.classes('text-red-500 text-green-600 text-blue-700')

# Background
.classes('bg-white bg-grey-1 bg-blue-50')
.classes('bg-primary')  # uses ui.colors() primary

# Border
.classes('border border-grey-3 border-primary rounded-lg')
```

### Flexbox
```python
# Container
with ui.row().classes('flex items-center justify-between gap-4 flex-wrap'):
    ...

# Alignment
.classes('items-start items-center items-end items-stretch')
.classes('justify-start justify-center justify-end justify-between')

# Child
.classes('flex-grow flex-shrink-0 flex-1')
.classes('self-start self-center self-end')
```

---

## 2. Common Layout Patterns

### Full-page app shell
```python
@ui.page('/')
def page():
    ui.query('.nicegui-content').classes('p-0')  # remove default padding

    with ui.header(elevated=True).classes('bg-primary text-white items-center px-6 h-14'):
        ui.label('MyApp').classes('text-xl font-bold')
        ui.space()
        ui.button(icon='account_circle').props('flat round color=white')

    with ui.left_drawer(bottom_corner=True).classes('bg-grey-1 pt-6') as drawer:
        for item in nav_items:
            with ui.item(on_click=lambda r=item['route']: ui.navigate.to(r)):
                with ui.item_section().props('avatar'):
                    ui.icon(item['icon'])
                with ui.item_section():
                    ui.item_label(item['label'])

    with ui.page_sticky('bottom-right', x_offset=20, y_offset=20):
        ui.button(icon='add', on_click=create_new).props('fab color=primary')

    with ui.column().classes('w-full max-w-5xl mx-auto px-4 py-6 gap-6'):
        yield  # main content goes here
```

### Centered card (login, onboarding)
```python
with ui.column().classes('absolute-center items-center gap-4'):
    with ui.card().classes('w-96 shadow-xl'):
        ...
```

### Two-column layout
```python
with ui.row().classes('w-full gap-6'):
    # Sidebar
    with ui.column().classes('w-64 shrink-0 gap-4'):
        ui.label('Sidebar')

    # Main content
    with ui.column().classes('flex-1 min-w-0 gap-4'):
        ui.label('Main content')
```

### Dashboard grid
```python
with ui.grid(columns=3).classes('w-full gap-4'):
    for metric in metrics:
        with ui.card().classes('p-4'):
            ui.label(metric['label']).classes('text-sm text-grey-6')
            ui.label(metric['value']).classes('text-3xl font-bold text-primary')
            ui.label(metric['change']).classes(
                'text-sm ' + ('text-green-600' if metric['change'] > 0 else 'text-red-600')
            )
```

### Sticky header with scrollable content
```python
with ui.column().classes('h-screen overflow-hidden'):
    with ui.row().classes('shrink-0 bg-white border-b px-4 py-2'):
        ui.label('Sticky Header')
    with ui.scroll_area().classes('flex-1'):
        # Long content
        for i in range(100):
            ui.label(f'Row {i}')
```

### Split pane
```python
with ui.splitter(value=30).classes('w-full h-96') as splitter:
    with splitter.before:
        with ui.column().classes('p-4 gap-2'):
            ui.label('Left Panel').classes('font-bold')
    with splitter.after:
        with ui.column().classes('p-4'):
            ui.label('Right Panel').classes('font-bold')
```

### Infinite scroll (virtual list)
```python
items = list(range(200))
page_size = 20
loaded = {'count': page_size}

@ui.refreshable
def item_list():
    for i in items[:loaded['count']]:
        ui.label(f'Item {i}').classes('py-2 border-b')

async def load_more():
    loaded['count'] = min(loaded['count'] + page_size, len(items))
    item_list.refresh()

item_list()
ui.button('Load More', on_click=load_more)
```

---

## 3. Theming with ui.colors()

Set Quasar's color palette at app start or per-page:

```python
# At startup (global)
ui.colors(
    primary='#1565C0',    # blue-800
    secondary='#00897B',  # teal-600
    accent='#8E24AA',     # purple-600
    positive='#2E7D32',   # green-800
    negative='#C62828',   # red-800
    info='#0277BD',       # light-blue-800
    warning='#E65100',    # deep-orange-800
)

# Per-page (overrides for that client)
@ui.page('/admin')
def admin_page():
    ui.colors(primary='#B71C1C')  # red theme for admin
    ...
```

**Use primary color in components:**
```python
ui.button('Action').props('color=primary')
ui.linear_progress().props('color=secondary')
ui.icon('star').classes('text-accent')
ui.label('Warning').classes('text-warning')
```

---

## 4. Dark Mode

```python
# Set globally at ui.run()
ui.run(dark=True)   # always dark
ui.run(dark=False)  # always light
ui.run(dark=None)   # follow OS preference (default)

# Toggle per-user at runtime
dark = ui.dark_mode()           # creates dark mode controller
dark.enable()                   # turn on
dark.disable()                  # turn off
dark.toggle()                   # flip

# Bind to a switch
ui.switch('Dark mode').bind_value_to(dark, 'value')

# Persist user preference
@ui.page('/')
def index():
    dark = ui.dark_mode()
    if app.storage.user.get('dark_mode'):
        dark.enable()
    ui.switch('Dark mode').on_value_change(
        lambda e: [dark.toggle(), app.storage.user.update({'dark_mode': e.value})]
    )
```

**Dark-aware classes:**
```python
# Tailwind dark variant
.classes('bg-white dark:bg-grey-9 text-grey-9 dark:text-white')
```

---

## 5. Props System (Quasar)

Props pass directly to the underlying Quasar component. Use `.props()`:

```python
# Input props
ui.input().props('outlined dense clearable rounded')
ui.input().props('type=password clearable')
ui.input().props('prepend-icon=search suffix-icon=mic')

# Button props
ui.button().props('flat outline round fab fab-mini')
ui.button().props('color=primary size=lg')
ui.button().props('no-caps')        # disable uppercase text
ui.button().props('loading')        # show spinner
ui.button().props(remove='loading') # remove spinner

# Table props
ui.table().props('flat bordered dense hide-header')
ui.table().props('virtual-scroll')  # enable virtual scrolling

# Select props
ui.select().props('use-input use-chips multiple clearable')
ui.select().props('outlined dense emit-value map-options')

# Common props for most components
.props('dense')    # compact mode
.props('flat')     # no shadow/border
.props('rounded')  # rounded corners
.props('square')   # square corners
```

**Remove a prop:**
```python
btn.props(remove='loading')
btn.props(remove='disabled')
```

---

## 6. Inline Styles

For CSS not available via Tailwind or props:

```python
ui.label().style('font-size: 3em; letter-spacing: 0.1em')
ui.image().style('width: 200px; height: 200px; object-fit: cover')
ui.column().style('background: linear-gradient(135deg, #667eea 0%, #764ba2 100%)')

# Multiple styles
element.style('border-left: 4px solid #6E93D6; padding-left: 12px')
```

**Dynamic styles:**
```python
# Bind style to data
label.style(f'color: {color}; font-weight: {"bold" if bold else "normal"}')
```

---

## 7. CSS Injection

### Global CSS
```python
# String (good for small additions)
ui.add_css('''
    .nicegui-content { padding: 0; }
    .my-card { border-radius: 12px; }
    a:link, a:visited { color: inherit; text-decoration: none; }
''')

# Tailwind arbitrary values
ui.add_css(r'''
    [&_a]:text-inherit [&_a]:no-underline
''')
```

### Head HTML (link to external CSS)
```python
ui.add_head_html('''
    <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap">
    <style>
        body { font-family: 'Inter', sans-serif; }
    </style>
''')
```

### Static files
```python
# Serve a directory as static files
from nicegui import app
app.add_static_files('/static', 'static')  # maps /static/* to ./static/*

# Use in templates:
ui.image('/static/logo.png')
ui.add_head_html('<link rel="stylesheet" href="/static/custom.css">')
```

---

## 8. Responsive Design

NiceGUI/Quasar uses breakpoints: `xs`(<600px), `sm`(600-1024px), `md`(1024-1440px), `lg`(1440-1920px), `xl`(>1920px).

```python
# Tailwind responsive prefixes
.classes('w-full md:w-96')        # full width on mobile, fixed on md+
.classes('grid-cols-1 md:grid-cols-2 lg:grid-cols-3')  # responsive grid
.classes('text-sm md:text-base lg:text-lg')

# Hide/show at breakpoints
.classes('hidden md:block')   # hide on mobile
.classes('block md:hidden')   # show on mobile only
```

**Detect mobile in Python:**
```python
@ui.page('/')
async def index():
    await ui.context.client.connected()
    is_mobile = await ui.run_javascript(
        'return window.innerWidth < 768'
    )
    if is_mobile:
        layout_mobile()
    else:
        layout_desktop()
```

---

## 9. Reusable Frames with Context Managers

Create reusable page shells using Python's `contextmanager`:

```python
from contextlib import contextmanager
from nicegui import ui, app

@contextmanager
def page_frame(title: str, nav_active: str = ''):
    """Reusable app shell with header, nav drawer, and content area."""
    ui.colors(primary='#1565C0')

    with ui.header(elevated=True).classes('bg-primary text-white items-center px-6 h-14'):
        ui.label('MyApp').classes('text-xl font-bold flex-grow')
        ui.label(f'Hello, {app.storage.user.get("username", "Guest")}').classes('text-sm')
        ui.button(icon='logout', on_click=logout).props('flat round color=white')

    with ui.left_drawer().classes('bg-white border-r'):
        _nav_drawer(nav_active)

    with ui.column().classes('w-full max-w-6xl mx-auto px-6 py-8 gap-6'):
        if title:
            ui.label(title).classes('text-3xl font-bold text-grey-9')
        yield


def _nav_drawer(active: str):
    nav_items = [
        ('/', 'home', 'Home'),
        ('/data', 'storage', 'Data'),
        ('/settings', 'settings', 'Settings'),
    ]
    with ui.column().classes('w-full gap-1 pt-4'):
        for route, icon, label in nav_items:
            is_active = active == route
            with ui.item(on_click=lambda r=route: ui.navigate.to(r)).classes(
                'rounded-lg ' + ('bg-primary text-white' if is_active else 'hover:bg-grey-2')
            ):
                with ui.item_section().props('avatar'):
                    ui.icon(icon, color='white' if is_active else 'grey')
                with ui.item_section():
                    ui.item_label(label)


# Usage
@ui.page('/')
def home():
    with page_frame('Dashboard', nav_active='/'):
        ui.label('Welcome!')

@ui.page('/data')
def data():
    with page_frame('Data', nav_active='/data'):
        ui.label('Data view')
```
