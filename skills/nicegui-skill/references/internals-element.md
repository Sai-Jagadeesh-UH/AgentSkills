# NiceGUI Internals — Element System

> Load when: subclassing Element, debugging missing updates, building custom components, understanding why a UI change didn't propagate.

## Table of Contents
1. [Element Anatomy](#1-element-anatomy)
2. [ID & Client Assignment](#2-id--client-assignment)
3. [Slot System & Context Stack](#3-slot-system--context-stack)
4. [Props / Classes / Style — Observable Setters](#4-props--classes--style--observable-setters)
5. [_to_dict() — What Gets Sent to Browser](#5-_to_dict--what-gets-sent-to-browser)
6. [update() Cycle](#6-update-cycle)
7. [Element Subclassing](#7-element-subclassing)
8. [Lifecycle & Deletion](#8-lifecycle--deletion)
9. [Common Debugging Patterns](#9-common-debugging-patterns)

---

## 1. Element Anatomy

Every NiceGUI widget is an `Element` (or subclass). Key attributes:

```python
class Element(Visibility):
    component: Component | None       # Vue/JS component descriptor (class-level)
    exposed_libraries: list[Library]  # JS libraries this class exposes

    # Per-instance
    id: int                           # unique within its Client
    tag: str                          # HTML/Vue tag name (e.g. 'q-btn', 'div')
    _classes: Classes                 # ObservableList → triggers update on change
    _style: Style                     # ObservableDict → triggers update on change
    _props: Props                     # ObservableDict → triggers update on change
    _markers: list[str]               # for ElementFilter / testing (.mark())
    _event_listeners: dict[str, EventListener]
    _text: str | None                 # inner text content
    slots: dict[str, Slot]            # named slots; 'default' always present
    default_slot: Slot
    _parent_slot: weakref[Slot] | None
    _update_method: str | None        # custom Vue method to call on update
    _deleted: bool
```

The `html_id` property returns `f'c{self.id}'` — the actual DOM id used by the browser (e.g. `c0`, `c42`).

---

## 2. ID & Client Assignment

```python
# element.py __init__
client = _client or context.client      # always resolved from slot stack
self.id = client.next_element_id        # auto-incrementing int per client
client.next_element_id += 1
client.elements[self.id] = self         # registered in client's element dict
```

**Implication:** element IDs restart from 0 for each new client/page visit. Never use `element.id` to uniquely identify an element across clients — use `element.html_id` + `client.id` together.

**Client reference is a weakref:**
```python
self._client = weakref.ref(client)

@property
def client(self) -> Client:
    client = self._client()
    if client is None:
        raise RuntimeError('The client has been deleted.')
    return client
```

---

## 3. Slot System & Context Stack

### How `with ui.row():` works

Every `with element:` call enters the element's **default slot**:

```python
def __enter__(self) -> Self:
    self.default_slot.__enter__()   # pushes slot onto stack
    return self

def __exit__(self, *_) -> None:
    self.default_slot.__exit__()    # pops slot from stack
```

### Slot Stack — per asyncio task

```python
# slot.py
class Slot:
    stacks: ClassVar[dict[int, list[Slot]]] = {}
    # key = id(asyncio.current_task()) or 0 if no task

    @classmethod
    def get_stack(cls) -> list[Slot]:
        task_id = id(asyncio.current_task()) if asyncio.current_task() else 0
        return cls.stacks.setdefault(task_id, [])
```

**Each asyncio task has its own slot stack** — this is how multiple concurrent page builds don't interfere. Background tasks have an empty stack, which is why `ui.label()` from a background task raises:
```
RuntimeError: The current slot cannot be determined because the slot stack is empty.
```
Fix: use `with client:` or `with some_container:` to enter the correct slot.

### Parent registration on element creation

```python
# element.py __init__
slot_stack = context.slot_stack
if slot_stack:
    parent_slot = slot_stack[-1]
    parent_slot.children.append(self)       # registered as child
    self._parent_slot = weakref.ref(parent_slot)

client.outbox.enqueue_update(self)          # send self to browser
if self._parent_slot:
    client.outbox.enqueue_update(parent_slot.parent)  # also update parent
```

### Named slots

```python
# Add a custom slot (used by ui.table, ui.expansion, etc.)
table.add_slot('header', '<q-th>{{ col.label }}</q-th>')

# Enter a named slot
with table.add_slot('body-cell-actions'):
    ui.button('Edit')
```

`_collect_slot_dict()` serializes non-default slots to `{name: {ids: [...], template?: "..."}}`.

---

## 4. Props / Classes / Style — Observable Setters

All three are `ObservableDict`/`ObservableList` subclasses that **auto-call `element.update()`** on any mutation:

```python
class Classes(ObservableList):
    def _update(self):
        element.update()     # → outbox.enqueue_update(element)

class Props(ObservableDict):
    def _update(self):
        element.update()

class Style(ObservableDict):
    def _update(self):
        element.update()
```

### `.classes()` call syntax

```python
# Fluent API — returns element for chaining
element.classes('text-lg font-bold')          # add
element.classes(remove='text-sm')             # remove
element.classes(toggle='hidden')              # toggle
element.classes(replace='text-xl text-blue')  # replace all

# Direct list mutation — also triggers update
element._classes.append('my-class')
element._classes[:] = ['text-xl']
```

### `.props()` string parsing

Props string is parsed by `Props.parse()` regex — supports:
- Boolean: `'dense'` → `{'dense': True}`
- Key=value: `'color=primary'` → `{'color': 'primary'}`
- Quoted: `'label="hello world"'` → `{'label': 'hello world'}`
- Complex: `':items="[1,2,3]"'` → `{':items': '[1,2,3]'}`

### `.style()` parsing

Semicolon-separated CSS: `'color: red; font-size: 16px'` → `{'color': 'red', 'font-size': '16px'}`

### Default class/style/props (class-level)

```python
class MyButton(ui.button):
    pass

MyButton.default_classes('bg-blue-500 text-white')
MyButton.default_props('no-caps dense')
MyButton.default_style('border-radius: 8px')

# All instances of MyButton get these by default
```

**These must be set before instantiation.** They're stored as `_default_classes`, `_default_props`, `_default_style` class variables, copied on each subclass.

---

## 5. _to_dict() — What Gets Sent to Browser

This method produces the JSON payload for the `update` Socket.IO message:

```python
def _to_dict(self) -> dict:
    return {
        'tag': self.tag,
        **({'text': self._text} if self._text is not None else {}),
        **{
            key: value
            for key, value in {
                'class': self._classes,     # list of strings
                'style': self._style,       # dict of CSS
                'props': self._props,       # dict of Quasar props
                'slots': self._collect_slot_dict(),  # non-default slots
                'children': [child.id for child in self.default_slot.children],
                'events': [listener.to_dict() for listener in self._event_listeners.values()],
                'update_method': self._update_method,
            }.items()
            if value  # omit empty/falsy values
        },
    }
```

**Key insight:** children are sent as **IDs only** (not nested objects). The browser reconstructs the tree from the flat `elements` dict sent in `build_response`.

**`update_method`**: some elements (like `ui.echart`) use a custom Vue update method instead of full re-render. Set `element._update_method = 'update'` to use the component's own update logic.

---

## 6. update() Cycle

```
Python: element.classes('text-lg')
         ↓
        Classes.__call__() → Classes[:] = new_list
         ↓
        ObservableList.__setitem__() → _handle_change()
         ↓
        Classes._update() → element.update()
         ↓
        Element.update() → client.outbox.enqueue_update(self)
         ↓
        Outbox.updates[element.id] = element  (WeakValueDict)
         ↓
        asyncio.Event.set() → wakes outbox loop
         ↓  (on next event loop tick)
        Outbox.loop() → collects all pending updates
         ↓
        emit('update', {id: element._to_dict(), ...})  via Socket.IO
         ↓
        Browser Vue patches DOM
```

**Batching:** all updates enqueued within one synchronous handler run are sent in a single `update` message. The outbox loop only runs between event loop ticks.

**Deleted elements:**
```python
def update(self) -> None:
    if self.is_deleted:
        return       # no-op — prevents updates after delete
    self.client.outbox.enqueue_update(self)
```

**Suspend updates** (Props/Classes/Style only):
```python
with element._props.suspend_updates():
    element._props['key1'] = 'v1'
    element._props['key2'] = 'v2'
# One update emitted after the with block
```

---

## 7. Element Subclassing

### Via `__init_subclass__` (automatic)

NiceGUI processes these keyword args on class definition:

```python
class MyWidget(Element,
               component='mywidget.vue',     # registers Vue SFC
               dependencies=['lib.js'],       # registers JS library
               esm={'key': 'module/index.js'}, # registers ESM module
               default_classes='p-4',
               default_style='color: red',
               default_props='dense'):
    pass
```

`component=` path is resolved relative to the subclass's file location.

### Minimal subclass pattern

```python
from pathlib import Path
from nicegui.element import Element

class SignaturePad(Element, component=Path(__file__).parent / 'signature_pad.vue'):

    def __init__(self, on_change=None):
        super().__init__()
        if on_change:
            self.on('change', on_change)

    def clear(self):
        self.run_method('clear')    # calls Vue component method

    @property
    def value(self):
        return self._props.get('modelValue', '')
```

### `run_method(name, *args)` — call Vue method

```python
# Returns AwaitableResponse
result = await element.run_method('getSelection')

# Fire and forget
element.run_method('scrollToBottom')
```

Internally: `client.run_javascript(f'return runMethod({self.id}, ...)')`.

### `get_computed_prop(name)` — read Vue computed

```python
value = await element.get_computed_prop('scrollHeight')
```

---

## 8. Lifecycle & Deletion

### Element deletion

```python
element.delete()
  → parent_slot.parent.remove(element)
    → client.remove_elements(element.descendants(include_self=True))
      → binding.remove(elements)       # unregister all bindings
      → element._handle_delete()       # clear slots + event_listeners
      → element._deleted = True
      → outbox.enqueue_delete(element) # sends None to browser → removes from DOM
      → client.elements.pop(element.id)
```

`_handle_delete()` can be overridden in subclasses for cleanup:
```python
class MyWidget(Element, component='my.vue'):
    def _handle_delete(self):
        super()._handle_delete()
        self._cleanup_resources()
```

### Checking if deleted

```python
if element.is_deleted:
    return  # safe guard

# element.client raises RuntimeError if client was GC'd
# element.parent_slot raises RuntimeError if parent was GC'd
```

### Client deletion cascade

When `client.delete()` is called (after reconnect_timeout expires):
1. Invokes all `delete_handlers`
2. `remove_all_elements()` → for each element: binding cleanup, `_handle_delete()`, outbox delete
3. `outbox.stop()` → stops the outbox background loop
4. `del Client.instances[self.id]`

---

## 9. Common Debugging Patterns

### "My UI isn't updating"

```python
# Check 1: Is element deleted?
print(element.is_deleted)  # True = update won't work

# Check 2: Is client connected?
print(element.client.has_socket_connection)  # False = updates queued but not sent

# Check 3: Are you in a background task without context?
# This raises RuntimeError: slot stack is empty
with element.client:         # enter client context manually
    element.text = 'updated'

# Check 4: Did you call update() after manual prop mutation?
element._props['myProp'] = 'value'  # doesn't auto-update
element.update()                     # required!
```

### "My with: nesting is wrong"

```python
# Check the slot stack for current task
from nicegui.slot import Slot
stack = Slot.get_stack()
print([s.name for s in stack])  # ['default', 'default', ...]
```

### "Element IDs in tests"

```python
# Find elements by marker (set with .mark())
from nicegui.element_filter import ElementFilter
buttons = ElementFilter(marker='save-btn')
# Or by type
labels = ElementFilter(kind=ui.label)
```

### Element tree inspection

```python
# Print the full element tree as string
print(str(client.layout))

# Iterate descendants
for el in client.content.descendants():
    print(el.id, el.tag, el._markers)
```
