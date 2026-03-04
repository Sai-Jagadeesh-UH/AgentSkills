# NiceGUI Components Reference

## Table of Contents
1. [Container Elements](#1-container-elements)
2. [Input Components](#2-input-components)
3. [Display Components](#3-display-components)
4. [Table & Data Components](#4-table--data-components)
5. [Media Components](#5-media-components)
6. [Navigation Components](#6-navigation-components)
7. [Feedback & Overlay](#7-feedback--overlay)
8. [Special Components](#8-special-components)

---

## 1. Container Elements

### `ui.column()` / `ui.row()`
Flex containers — vertical and horizontal.

```python
with ui.column().classes('w-full gap-4'):
    ui.label('Item 1')
    ui.label('Item 2')

with ui.row().classes('items-center gap-2 flex-wrap'):
    ui.icon('star')
    ui.label('Rating')
```

### `ui.card()`
Quasar QCard with shadow and padding.

```python
with ui.card().classes('w-full max-w-md shadow-lg'):
    with ui.card_section():
        ui.label('Title').classes('text-h6')
    ui.separator()
    with ui.card_section():
        ui.label('Body content')
    with ui.card_actions().props('align=right'):
        ui.button('OK', on_click=dialog.close)
```

### `ui.expansion()`
Collapsible accordion panel.

```python
with ui.expansion('Details', icon='info', value=False).classes('w-full'):
    ui.label('Expanded content here')
```

### `ui.scroll_area()`
Scrollable container with custom scrollbar.

```python
with ui.scroll_area().classes('h-64 w-full border'):
    for i in range(50):
        ui.label(f'Item {i}')
```

### `ui.splitter()`
Resizable split pane.

```python
with ui.splitter() as splitter:
    with splitter.before:
        ui.label('Left panel')
    with splitter.after:
        ui.label('Right panel')
```

### `ui.grid()`
CSS Grid layout.

```python
with ui.grid(columns=3).classes('w-full gap-4'):
    for i in range(9):
        with ui.card():
            ui.label(f'Cell {i}')
```

---

## 2. Input Components

### `ui.input()`
Text input. Supports password, clearable, prefix/suffix icons.

```python
# Basic
name = ui.input('Full Name', placeholder='Jane Doe').classes('w-full')

# Password
pwd = ui.input('Password').props('type=password clearable').classes('w-full')

# With validation
email = ui.input('Email', validation={'Invalid email': lambda v: '@' in v})

# With prefix icon
search = ui.input(placeholder='Search...').props('outlined dense')
search.props('prepend-icon=search')

# Enter key handler
ui.input('Message').on('keydown.enter', lambda e: send(e.sender.value))
```

### `ui.textarea()`
Multi-line text input.

```python
bio = ui.textarea('Bio', placeholder='Tell us about yourself').classes('w-full')
bio.props('rows=5 autogrow')
```

### `ui.number()`
Numeric input with min/max/step.

```python
qty = ui.number('Quantity', value=1, min=0, max=100, step=1).classes('w-48')
price = ui.number('Price', value=9.99, format='%.2f', prefix='$')
```

### `ui.checkbox()`
Boolean toggle with label.

```python
remember = ui.checkbox('Remember me', value=False)
# Access value: remember.value
```

### `ui.switch()`
Toggle switch (visually different from checkbox).

```python
dark = ui.switch('Dark mode').bind_value(app.storage.user, 'dark_mode')
```

### `ui.slider()`
Range slider.

```python
volume = ui.slider(min=0, max=100, value=50, step=5).classes('w-64')
ui.label().bind_text_from(volume, 'value', backward=lambda v: f'Volume: {v}%')
```

### `ui.range()`
Dual-handle range selector.

```python
price_range = ui.range(min=0, max=1000, value={'min': 100, 'max': 500})
```

### `ui.select()`
Dropdown with optional filtering.

```python
# Static options
color = ui.select(['red', 'green', 'blue'], label='Color', value='blue')

# With labels (value, label pairs)
status = ui.select(
    options=[{'value': 1, 'label': 'Active'}, {'value': 0, 'label': 'Inactive'}],
    label='Status', value=1
)

# With filtering
country = ui.select(options=country_list, label='Country').props('use-input clearable')
```

### `ui.toggle()`
Button group for single selection.

```python
view = ui.toggle(['list', 'grid', 'table'], value='list')
# view.value gives current selection
```

### `ui.radio()`
Radio button group.

```python
size = ui.radio(['small', 'medium', 'large'], value='medium').props('inline')
```

### `ui.date()` / `ui.time()`
Date and time pickers.

```python
date = ui.date(value='2024-01-15').props('landscape')
time = ui.time(value='12:00')
```

### `ui.color_input()` / `ui.color_picker()`
Color selection.

```python
color = ui.color_input('Theme color', value='#6E93D6').classes('w-48')
```

### `ui.upload()`
File upload with drag-and-drop support.

```python
async def handle_upload(e: events.UploadEventArguments):
    content = await e.file.read()
    name = e.name
    mime = e.type
    ui.notify(f'Uploaded {name} ({len(content)} bytes)')

ui.upload(
    label='Drop files here',
    on_upload=handle_upload,
    auto_upload=True,         # upload immediately on select
    multiple=True,
    max_file_size=10_000_000, # 10MB
).classes('w-full')
```

### `ui.button()`
Clickable button. Accepts icon, color, props.

```python
# Basic
ui.button('Save', on_click=save_data)

# With icon
ui.button('Delete', icon='delete', on_click=delete_item).props('color=negative flat')

# Loading state
btn = ui.button('Process', on_click=run_task)

async def run_task():
    btn.props('loading')
    await heavy_work()
    btn.props(remove='loading')

# Icon-only (FAB style)
ui.button(icon='add', on_click=add_item).props('fab color=primary')
```

### `ui.link()`
Hyperlink — to URL or internal route.

```python
ui.link('NiceGUI Docs', 'https://nicegui.io', new_tab=True)
ui.link('Go to Settings', '/settings')
```

---

## 3. Display Components

### `ui.label()`
Text display. Supports Tailwind classes.

```python
ui.label('Hello').classes('text-2xl font-bold text-primary')
ui.label('Status').classes('text-sm text-grey-6 uppercase tracking-wider')
```

### `ui.markdown()`
Render Markdown with optional code highlighting.

```python
ui.markdown('''
# Title
Some **bold** and *italic* text.

```python
print("hello")
```
''')
```

### `ui.html()`
Raw HTML. Use `sanitize=True` for user content.

```python
ui.html('<strong>Bold</strong> and <em>italic</em>')
# With sanitization (safe for user input)
from html_sanitizer import Sanitizer
ui.html(user_input, sanitize=Sanitizer().sanitize)
```

### `ui.code()`
Code block with syntax highlighting and copy button.

```python
ui.code('print("Hello World")', language='python')
ui.code(json.dumps(data, indent=2), language='json')
```

### `ui.icon()`
Material Design icon.

```python
ui.icon('home', size='2rem', color='primary')
ui.icon('check_circle').classes('text-green-500 text-3xl')
```

### `ui.avatar()`
User avatar — image or text initials.

```python
ui.avatar('AB', color='primary', text_color='white')
ui.avatar(icon='person', size='3rem')
# From URL:
ui.avatar(src='https://example.com/photo.jpg')
```

### `ui.badge()`
Small count/status indicator, usually on an icon.

```python
with ui.button(icon='notifications'):
    ui.badge(str(count), color='red').props('floating')
```

### `ui.chip()`
Tag / keyword chip.

```python
ui.chip('Python', icon='code', color='blue', text_color='white')
```

### `ui.spinner()`
Loading indicator.

```python
ui.spinner()               # default circle
ui.spinner(type='dots')    # three bouncing dots
ui.spinner(type='comment') # comment bubble
ui.spinner(size='xl', color='primary')
```

### `ui.linear_progress()`
Horizontal progress bar.

```python
progress = ui.linear_progress(value=0.0, show_value=True).classes('w-full')
# Update:
progress.value = 0.75  # 75%
# Or bind:
progress.bind_value_from(worker, 'progress')
```

### `ui.circular_progress()`
Circular progress indicator.

```python
ui.circular_progress(value=0.6, min=0, max=1, size='xl', color='primary')
```

### `ui.log()`
Scrolling log output.

```python
log = ui.log(max_lines=100).classes('w-full h-48 font-mono text-sm')
log.push('Server started')
log.push(f'[{datetime.now()}] Request received')
```

### `ui.separator()`
Horizontal divider line.

```python
ui.separator()
ui.separator().classes('my-4')
```

### `ui.space()`
Flexible spacer (like CSS `flex-grow: 1`).

```python
with ui.row().classes('w-full'):
    ui.label('Left')
    ui.space()
    ui.label('Right')
```

### `ui.image()`
Image display with lazy loading.

```python
ui.image('https://example.com/photo.jpg').classes('w-full rounded-lg')
ui.image('/static/logo.png').classes('w-32 h-32 object-cover')
```

### `ui.interactive_image()`
Image with SVG overlay for drawing/annotations.

```python
img = ui.interactive_image(
    'https://picsum.photos/640/360',
    on_mouse=handle_mouse,
    cross=True,  # crosshair cursor
)
# Draw SVG on top:
img.content = '<circle cx="100" cy="100" r="20" fill="red" />'
```

---

## 4. Table & Data Components

### `ui.table()`
Quasar QTable — sortable, filterable, paginated, selectable.

```python
columns = [
    {'name': 'id', 'label': '#', 'field': 'id', 'sortable': True, 'align': 'left'},
    {'name': 'name', 'label': 'Name', 'field': 'name', 'sortable': True},
    {'name': 'status', 'label': 'Status', 'field': 'status'},
]
rows = [
    {'id': 1, 'name': 'Alice', 'status': 'active'},
    {'id': 2, 'name': 'Bob', 'status': 'inactive'},
]

table = ui.table(
    columns=columns,
    rows=rows,
    row_key='id',
    selection='multiple',    # 'single' or 'multiple'
    pagination=10,           # rows per page
).classes('w-full')

# Top-right search
with table.add_slot('top-right'):
    ui.input(placeholder='Search').props('dense clearable').bind_value(table, 'filter')

# Custom cell rendering (body slot)
with table.add_slot('body'):
    with ui.tr():
        with ui.td():
            ui.badge(table.row['status'])

# Bottom add-row
with table.add_slot('bottom-row'):
    with ui.tr():
        with ui.td():
            new_name = ui.input(placeholder='New name').props('dense')
        with ui.td():
            ui.button(icon='add', on_click=lambda: add_row(new_name.value)).props('flat')

# Access selected rows
selected = table.selected  # list of dicts
```

### `ui.aggrid()`
AG Grid — full-featured editable data grid.

```python
grid = ui.aggrid({
    'columnDefs': [
        {'field': 'name', 'editable': True, 'sortable': True, 'filter': True},
        {'field': 'age', 'editable': True, 'type': 'numericColumn'},
        {
            'field': 'actions',
            'cellRenderer': 'agButtonCellRenderer',  # custom renderer
        }
    ],
    'rowData': rows,
    'stopEditingWhenCellsLoseFocus': True,
    'rowSelection': 'multiple',
    'animateRows': True,
    'defaultColDef': {'resizable': True, 'flex': 1},
}).classes('ag-theme-alpine w-full h-96')

# Get updated rows after editing
async def save():
    rows = await grid.get_selected_rows()
    all_rows = await grid.run_grid_method('getRenderedNodes')
```

### `ui.tree()`
Hierarchical tree structure.

```python
nodes = [
    {'id': 'root', 'label': 'Root', 'children': [
        {'id': 'child1', 'label': 'Child 1'},
        {'id': 'child2', 'label': 'Child 2', 'children': [
            {'id': 'grandchild', 'label': 'Grandchild'}
        ]},
    ]},
]

tree = ui.tree(nodes, node_key='id', label_key='label', on_select=handle_select)
tree.expand()  # expand all

# Custom node rendering with slot
with tree.add_slot('default-header'):
    with ui.row().classes('items-center'):
        ui.icon(tree.node['icon'] if 'icon' in tree.node else 'folder')
        ui.label(tree.node['label'])
```

### `ui.json_editor()`
JSON editor (Monaco/JSON Schema based).

```python
editor = ui.json_editor({'content': {'json': {'key': 'value'}}})
data = await editor.run_editor_method('get')
```

---

## 5. Media Components

### `ui.video()`
HTML5 video player.

```python
ui.video('/static/demo.mp4', autoplay=False, controls=True).classes('w-full')
```

### `ui.audio()`
HTML5 audio player.

```python
ui.audio('/static/sound.mp3').props('controls')
```

### `ui.scene()`
3D WebGL scene using Three.js.

```python
with ui.scene(width=800, height=500) as scene:
    # Lighting
    scene.ambient_light(intensity=0.5)
    scene.spot_light(distance=100, intensity=0.3).move(10, 10, 10)

    # Primitives
    scene.sphere(radius=1).move(x=0).material('#4488ff')
    scene.box(1, 1, 1).move(x=3).material('#ff4444')
    scene.cylinder(1, 2).move(x=-3)

    # STL model
    scene.stl('/static/model.stl').scale(0.1).move(-2, 0, 0)

    # Group for hierarchy
    group = scene.group().move(0, 0, 2)
    with group:
        scene.sphere(0.5).material('#44ff44')

    # Camera
    scene.move_camera(x=5, y=5, z=5, look_at_x=0, look_at_y=0, look_at_z=0)
```

### `ui.svg()`
Inline SVG rendering.

```python
ui.html('''<svg width="100" height="100">
  <circle cx="50" cy="50" r="40" fill="blue" />
</svg>''', sanitize=False)
```

---

## 6. Navigation Components

### `ui.header()` / `ui.footer()`
Page-level header and footer bars.

```python
with ui.header(elevated=True).classes('bg-primary text-white'):
    ui.label('App Name').classes('text-xl font-bold')
    ui.space()
    ui.button(icon='menu', on_click=drawer.toggle).props('flat round color=white')
```

### `ui.left_drawer()` / `ui.right_drawer()`
Side navigation panels.

```python
with ui.left_drawer(value=False).classes('bg-grey-1 pt-4') as drawer:
    with ui.column().classes('w-full px-4 gap-2'):
        ui.label('Navigation').classes('text-caption text-grey-6 uppercase')
        ui.separator()
        for item in nav_items:
            ui.link(item['label'], item['route']).classes(
                'text-primary no-underline font-medium py-2'
            )
```

### `ui.tabs()` + `ui.tab_panels()`
Tab-based navigation.

```python
with ui.tabs().classes('w-full') as tabs:
    t1 = ui.tab('home', label='Home', icon='home')
    t2 = ui.tab('data', label='Data', icon='storage')
    t3 = ui.tab('settings', label='Settings', icon='settings')

with ui.tab_panels(tabs, value=t1).classes('w-full flex-grow'):
    with ui.tab_panel(t1):
        home_content()
    with ui.tab_panel(t2):
        data_content()
    with ui.tab_panel(t3):
        settings_content()
```

### `ui.menu()`
Dropdown context menu.

```python
with ui.button(icon='more_vert').props('flat round'):
    with ui.menu():
        ui.menu_item('Edit', on_click=edit)
        ui.menu_item('Duplicate', on_click=duplicate)
        ui.separator()
        ui.menu_item('Delete', on_click=delete).classes('text-negative')
```

### `ui.breadcrumbs()`
Navigation breadcrumbs.

```python
with ui.breadcrumbs():
    ui.breadcrumb_el('Home', icon='home', href='/')
    ui.breadcrumb_el('Users', href='/users')
    ui.breadcrumb_el('Alice')
```

### `ui.pagination()`
Page number navigation.

```python
page_num = ui.pagination(1, max_pages, direction_links=True).bind_value(state, 'page')
```

### `ui.stepper()`
Step-by-step workflow UI.

```python
with ui.stepper().props('vertical') as stepper:
    with ui.step('Info', icon='person'):
        ui.label('Personal information')
        with ui.stepper_navigation():
            ui.button('Next', on_click=stepper.next)

    with ui.step('Review', icon='preview'):
        ui.label('Review your submission')
        with ui.stepper_navigation():
            ui.button('Back', on_click=stepper.previous).props('flat')
            ui.button('Submit', on_click=submit)
```

---

## 7. Feedback & Overlay

### `ui.notify()`
Toast notification (top-right by default).

```python
ui.notify('Saved successfully!', type='positive')
ui.notify('Error occurred', type='negative', timeout=5000)
ui.notify('Processing...', type='ongoing', spinner=True)
ui.notify('Info message', type='info', position='bottom')
# Types: positive, negative, warning, info, ongoing
# Positions: top-left, top-right, bottom-left, bottom-right, top, bottom, center
```

### `ui.dialog()`
Modal dialog. Use `await dialog` to get result.

```python
async def confirm_delete(item_name: str) -> bool:
    with ui.dialog() as dialog, ui.card().classes('w-80'):
        ui.label(f'Delete "{item_name}"?').classes('text-lg font-medium')
        ui.label('This action cannot be undone.').classes('text-grey-6')
        with ui.row().classes('w-full justify-end gap-2 mt-4'):
            ui.button('Cancel', on_click=lambda: dialog.submit(False)).props('flat')
            ui.button('Delete', on_click=lambda: dialog.submit(True)).props('color=negative')
    return await dialog
```

### `ui.tooltip()`
Hover tooltip on parent element.

```python
ui.button(icon='info').classes('text-grey').tooltip('Click for more information')
with ui.icon('help'):
    ui.tooltip('This field is required')
```

---

## 8. Special Components

### `ui.keyboard()`
Global keyboard shortcut handler.

```python
def handle_key(e: events.KeyEventArguments):
    if e.action.keydown:
        if e.key.escape:
            close_dialog()
        if e.modifiers.ctrl and e.key.s:
            save()

ui.keyboard(on_key=handle_key)
```

### `ui.timer()`
Periodic or one-shot callback.

```python
# Repeating
ui.timer(0.5, update_chart)

# One-shot after delay
ui.timer(2.0, show_welcome, once=True)

# Start/stop
timer = ui.timer(1.0, callback, active=False)
ui.button('Start', on_click=timer.activate)
ui.button('Stop', on_click=timer.deactivate)
```

### `ui.query()`
CSS selector-based element manipulation.

```python
# Style the main content area
ui.query('.nicegui-content').classes('p-0 bg-grey-1')
# Hide scrollbar
ui.query('body').style('overflow: hidden')
```

### `ui.add_head_html()` / `ui.add_body_html()`
Inject HTML into `<head>` or `<body>`.

```python
ui.add_head_html('<link rel="stylesheet" href="/static/custom.css">')
ui.add_body_html('<script src="/static/chart.js"></script>')
```

### `ui.run_javascript()`
Execute JavaScript and optionally await a return value.

```python
# Fire and forget
ui.run_javascript('window.scrollTo(0, document.body.scrollHeight)')

# Await a result
is_mobile = await ui.run_javascript(
    'return /iPhone|iPad|Android/.test(navigator.userAgent)'
)

# With timeout
try:
    result = await ui.run_javascript('return window.myFunc()', timeout=5.0)
except TimeoutError:
    pass
```

### `ui.page_sticky()`
Fixed-position overlay (FAB buttons, etc.).

```python
with ui.page_sticky(position='bottom-right', x_offset=20, y_offset=20):
    ui.button(icon='add', on_click=add_item).props('fab color=primary')
```

### `ui.colors()`
Set global Quasar color palette.

```python
ui.colors(
    primary='#6E93D6',
    secondary='#53B689',
    accent='#9C27B0',
    dark='#1d1d1d',
    positive='#21BA45',
    negative='#C10015',
    info='#31CCEC',
    warning='#F2C037',
)
```
