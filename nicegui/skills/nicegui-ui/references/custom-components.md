# NiceGUI Custom Components Reference

## Table of Contents
1. [Element Subclassing](#1-element-subclassing)
2. [Vue SFC Components](#2-vue-sfc-components)
3. [JavaScript ESM Components](#3-javascript-esm-components)
4. [Drag & Drop Kanban](#4-drag--drop-kanban)
5. [Slots — Custom Rendering](#5-slots--custom-rendering)
6. [Custom Events Between JS and Python](#6-custom-events-between-js-and-python)

---

## 1. Element Subclassing

Extend any NiceGUI element to add behavior or styling:

### Simple styled subclass
```python
from nicegui import ui

class PrimaryButton(ui.button):
    def __init__(self, label: str, **kwargs):
        super().__init__(label, **kwargs)
        self.props('color=primary no-caps')
        self.classes('px-6')


class DangerButton(ui.button):
    def __init__(self, label: str, **kwargs):
        super().__init__(label, **kwargs)
        self.props('color=negative flat no-caps')


class StatusBadge(ui.badge):
    STATUS_COLORS = {
        'active': 'green',
        'inactive': 'grey',
        'error': 'red',
        'warning': 'orange',
        'pending': 'blue',
    }

    def __init__(self, status: str):
        color = self.STATUS_COLORS.get(status, 'grey')
        super().__init__(status, color=color)
        self.classes('capitalize')


# Usage
PrimaryButton('Save', on_click=save)
DangerButton('Delete', on_click=delete)
StatusBadge('active')
```

### Composite component
```python
class MetricCard(ui.card):
    """A stat card showing label, value, change."""

    def __init__(self, label: str, value: str, change: float = 0.0):
        super().__init__()
        self.classes('p-4 min-w-40')
        with self:
            ui.label(label).classes('text-xs text-grey-6 uppercase tracking-wider')
            self._value_label = ui.label(value).classes('text-3xl font-bold mt-1')
            sign = '+' if change >= 0 else ''
            color = 'text-green-600' if change >= 0 else 'text-red-600'
            ui.label(f'{sign}{change:.1f}%').classes(f'text-sm {color}')

    def update_value(self, new_value: str):
        self._value_label.text = new_value


# Usage
card = MetricCard('Revenue', '$12,400', change=5.2)
ui.timer(60, lambda: card.update_value('$12,850'))
```

### Bindable custom element
```python
from nicegui.binding import BindableProperty

class TemperatureGauge(ui.column):
    temperature = BindableProperty(
        on_change=lambda sender, value: sender._update(value)
    )

    def __init__(self, min_temp=0, max_temp=100):
        super().__init__()
        self.min_temp = min_temp
        self.max_temp = max_temp
        self.temperature = min_temp
        with self:
            self._label = ui.label('--°C').classes('text-2xl font-bold')
            self._progress = ui.linear_progress(value=0).classes('w-full')
            self._status = ui.label('').classes('text-sm')

    def _update(self, value: float):
        self._label.text = f'{value:.1f}°C'
        normalized = (value - self.min_temp) / (self.max_temp - self.min_temp)
        self._progress.value = max(0, min(1, normalized))
        if value < 30:
            self._status.text = 'Normal'
            self._status.classes('text-green-600', remove='text-orange-600 text-red-600')
        elif value < 70:
            self._status.text = 'Warning'
            self._status.classes('text-orange-600', remove='text-green-600 text-red-600')
        else:
            self._status.text = 'Critical'
            self._status.classes('text-red-600', remove='text-green-600 text-orange-600')


# Usage with binding
sensor_data = {'temp': 25.0}
gauge = TemperatureGauge(min_temp=0, max_temp=100)
gauge.bind_value_from(sensor_data, 'temp')  # auto-updates when dict changes
```

---

## 2. Vue SFC Components

Create `.vue` files alongside your Python script and register them as NiceGUI elements:

### File structure
```
my_app/
├── main.py
├── audio_recorder.vue
└── canvas_editor.vue
```

### Vue component (audio_recorder.vue)
```vue
<template>
  <div class="audio-recorder">
    <button @click="toggleRecording" :class="{ recording: isRecording }">
      {{ isRecording ? 'Stop' : 'Record' }}
    </button>
    <span>{{ status }}</span>
  </div>
</template>

<script>
export default {
  data() {
    return {
      isRecording: false,
      mediaRecorder: null,
      chunks: [],
      status: 'Ready',
    };
  },
  methods: {
    async startRecording() {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      this.mediaRecorder = new MediaRecorder(stream);
      this.chunks = [];
      this.mediaRecorder.ondataavailable = e => this.chunks.push(e.data);
      this.mediaRecorder.onstop = () => this.sendAudio();
      this.mediaRecorder.start();
      this.isRecording = true;
      this.status = 'Recording...';
    },
    stopRecording() {
      this.mediaRecorder.stop();
      this.isRecording = false;
      this.status = 'Processing...';
    },
    toggleRecording() {
      if (this.isRecording) this.stopRecording();
      else this.startRecording();
    },
    async sendAudio() {
      const blob = new Blob(this.chunks, { type: 'audio/webm' });
      const arrayBuffer = await blob.arrayBuffer();
      const bytes = new Uint8Array(arrayBuffer);
      // Send to Python via custom event
      this.$emit('audio_ready', { data: Array.from(bytes) });
      this.status = 'Done';
    },
  },
};
</script>
```

### Python wrapper (main.py)
```python
from nicegui import ui, events

class AudioRecorder(ui.element, component='audio_recorder.vue'):
    def __init__(self, on_audio_ready=None):
        super().__init__()
        self._on_audio_ready = on_audio_ready
        self.on('audio_ready', self._handle_audio)

    def _handle_audio(self, e: events.GenericEventArguments):
        audio_bytes = bytes(e.args['data'])
        if self._on_audio_ready:
            self._on_audio_ready(audio_bytes)

    def start_recording(self):
        self.run_method('startRecording')

    def stop_recording(self):
        self.run_method('stopRecording')


# Usage
def process_audio(audio_bytes: bytes):
    ui.notify(f'Got {len(audio_bytes)} bytes of audio')

recorder = AudioRecorder(on_audio_ready=process_audio)
```

### Vue component with props from Python
```vue
<!-- counter.vue -->
<template>
  <div>
    <button @click="decrement">-</button>
    <span>{{ count }}</span>
    <button @click="increment">+</button>
  </div>
</template>

<script>
export default {
  props: ['value'],
  data() { return { count: this.value || 0 }; },
  methods: {
    increment() { this.count++; this.$emit('update', { value: this.count }); },
    decrement() { this.count--; this.$emit('update', { value: this.count }); },
  },
};
</script>
```

```python
class Counter(ui.element, component='counter.vue'):
    def __init__(self, value: int = 0, on_change=None):
        super().__init__()
        self._props['value'] = value
        if on_change:
            self.on('update', lambda e: on_change(e.args['value']))

    async def get_value(self) -> int:
        return await self.run_method('getValue')

Counter(value=5, on_change=lambda v: print(f'Count: {v}'))
```

---

## 3. JavaScript ESM Components

For components using modern ES modules (npm packages):

```javascript
// counter.js (ESM)
import { isOdd } from 'is-odd';  // npm package

export default {
  template: `<div>
    <button @click="count++">Count: {{ count }}</button>
    <p>Is odd: {{ isOdd(count) }}</p>
  </div>`,
  data() { return { count: 0 }; },
  methods: {
    isEven(n) { return !isOdd(n); },
    reset() { this.count = 0; },
  },
};
```

```python
class Counter(ui.element, component='counter.js', esm={'is-odd': 'node_modules/is-odd/index.js'}):
    async def is_even(self, number: int) -> bool:
        return await self.run_method('isEven', number)

    async def reset(self):
        await self.run_method('reset')
```

---

## 4. Drag & Drop Kanban

Full drag-and-drop example (Trello-style cards):

```python
from nicegui import ui, events

# Shared state
boards = {
    'todo': ['Task 1', 'Task 2', 'Task 3'],
    'in_progress': ['Task 4'],
    'done': ['Task 5'],
}
dragged_item: str | None = None
source_board: str | None = None


class KanbanCard(ui.card):
    def __init__(self, text: str, board_id: str):
        super().__init__()
        self.text = text
        self.board_id = board_id
        self.classes('w-full cursor-grab active:cursor-grabbing shadow-sm hover:shadow-md transition-shadow')

        with self:
            ui.label(text).classes('text-sm')

        self.props('draggable=true')
        self.on('dragstart', self._dragstart)

    def _dragstart(self, e):
        global dragged_item, source_board
        dragged_item = self.text
        source_board = self.board_id


class KanbanColumn(ui.column):
    COLUMN_LABELS = {
        'todo': 'To Do',
        'in_progress': '🔄 In Progress',
        'done': '✅ Done',
    }

    def __init__(self, board_id: str):
        super().__init__()
        self.board_id = board_id
        self.classes('w-64 bg-grey-2 rounded-lg p-3 gap-2 min-h-64')

        self.on('dragover.prevent', self._highlight)
        self.on('dragleave', self._unhighlight)
        self.on('drop', self._drop)

    def _highlight(self, e):
        self.classes('ring-2 ring-primary')

    def _unhighlight(self, e):
        self.classes(remove='ring-2 ring-primary')

    def _drop(self, e):
        global dragged_item, source_board
        self._unhighlight(e)

        if dragged_item and source_board and source_board != self.board_id:
            boards[source_board].remove(dragged_item)
            boards[self.board_id].append(dragged_item)
            kanban_board.refresh()

        dragged_item = None
        source_board = None

    def add_header(self):
        with ui.row().classes('w-full items-center justify-between'):
            ui.label(self.COLUMN_LABELS.get(self.board_id, self.board_id)).classes('font-semibold')
            ui.badge(str(len(boards[self.board_id])), color='grey')


@ui.refreshable
def kanban_board():
    with ui.row().classes('gap-4 items-start'):
        for board_id in ['todo', 'in_progress', 'done']:
            col = KanbanColumn(board_id)
            with col:
                col.add_header()
                for task in boards[board_id]:
                    KanbanCard(task, board_id)
                # Add card button
                with ui.row().classes('w-full items-center mt-1'):
                    new_task = ui.input(placeholder='Add card...').props('dense outlined').classes('flex-1 text-sm')
                    def add_card(bid=board_id, inp=new_task):
                        if inp.value:
                            boards[bid].append(inp.value)
                            kanban_board.refresh()
                    ui.button(icon='add', on_click=add_card).props('flat round dense')


kanban_board()
```

---

## 5. Slots — Custom Rendering

NiceGUI elements expose Quasar slots for custom rendering:

### Table body slot
```python
columns = [
    {'name': 'name', 'label': 'Name', 'field': 'name'},
    {'name': 'status', 'label': 'Status', 'field': 'status'},
    {'name': 'actions', 'label': 'Actions'},
]

with ui.table(columns=columns, rows=rows, row_key='id') as table:
    with table.add_slot('body'):
        with ui.tr(props='key=row.id'):
            ui.td('{{ row.name }}')
            with ui.td():
                # Badge per status
                ui.badge('{{ row.status }}').props(
                    ":color=\"row.status === 'active' ? 'green' : 'red'\""
                )
            with ui.td():
                ui.button('Edit').props('flat dense size=sm')
                ui.button('Delete').props('flat dense size=sm color=negative')
```

### Select option slot
```python
options = [{'value': 'us', 'label': 'United States', 'flag': '🇺🇸'}]

with ui.select(options, label='Country') as sel:
    with sel.add_slot('option'):
        with ui.item(props='v-bind="scope.itemProps"'):
            with ui.item_section().props('avatar'):
                ui.label('{{ scope.opt.flag }}')
            with ui.item_section():
                ui.item_label('{{ scope.opt.label }}')
```

### Tree custom node
```python
nodes = [
    {'id': '1', 'label': 'root.py', 'icon': 'code', 'type': 'file'},
    {'id': '2', 'label': 'src/', 'icon': 'folder', 'type': 'folder', 'children': [
        {'id': '3', 'label': 'main.py', 'icon': 'code', 'type': 'file'},
    ]},
]

with ui.tree(nodes, node_key='id', label_key='label') as tree:
    with tree.add_slot('default-header'):
        with ui.row().classes('items-center gap-1'):
            ui.icon('{{ node.icon }}').classes('text-sm')
            ui.label('{{ node.label }}').classes(
                "text-primary font-medium" if "type === 'folder'" else "text-sm"
            )
```

---

## 6. Custom Events Between JS and Python

### Python → JavaScript (run_method)
```python
class SignaturePad(ui.element, component='signature_pad.vue'):
    def clear(self):
        self.run_method('clear')

    def undo(self):
        self.run_method('undo')

    async def get_image_data(self, format: str = 'image/png') -> str:
        """Returns base64 data URL."""
        return await self.run_method('toDataURL', format)

    async def is_empty(self) -> bool:
        return await self.run_method('isEmpty')


pad = SignaturePad()
ui.button('Clear', on_click=pad.clear)

async def save_signature():
    if await pad.is_empty():
        ui.notify('Please sign first', type='warning')
        return
    data_url = await pad.get_image_data()
    # data_url is a base64 PNG
    import base64
    image_bytes = base64.b64decode(data_url.split(',')[1])
    Path('signature.png').write_bytes(image_bytes)

ui.button('Save', on_click=save_signature).props('color=primary')
```

### JavaScript → Python (emit events)
```vue
<!-- In .vue component -->
<script>
export default {
  methods: {
    onSelectionChange(items) {
      this.$emit('selection_changed', { items, count: items.length });
    },
    onError(message) {
      this.$emit('error', { message, timestamp: Date.now() });
    },
  },
};
</script>
```

```python
class MyGrid(ui.element, component='my_grid.vue'):
    def __init__(self, on_select=None, on_error=None):
        super().__init__()
        if on_select:
            self.on('selection_changed', lambda e: on_select(e.args['items']))
        if on_error:
            self.on('error', lambda e: on_error(e.args['message']))


MyGrid(
    on_select=lambda items: ui.notify(f'Selected {len(items)} items'),
    on_error=lambda msg: ui.notify(msg, type='negative'),
)
```

### Global JS events → Python
```python
# Fire from JavaScript
ui.add_body_html('''
<script>
document.addEventListener('paste', function(e) {
    const text = e.clipboardData.getData('text/plain');
    emitEvent('paste_event', { text });
});
</script>
''')

# Handle in Python
def on_paste(e):
    pasted_text = e.args.get('text', '')
    textarea.value += pasted_text

ui.on('paste_event', on_paste)
```
