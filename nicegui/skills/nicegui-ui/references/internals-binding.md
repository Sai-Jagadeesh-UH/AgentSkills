# NiceGUI Internals — Binding & Reactivity System

> Load when: debugging broken bindings, building custom reactive data models, understanding why bind_value lags, optimizing binding performance, using BindableProperty or bindable_dataclass.

## Table of Contents
1. [Two Types of Bindings](#1-two-types-of-bindings)
2. [active_links — Polled Bindings](#2-active_links--polled-bindings)
3. [bindings dict — Event-Driven Propagation](#3-bindings-dict--event-driven-propagation)
4. [BindableProperty — Property Descriptor](#4-bindableproperty--property-descriptor)
5. [ObservableCollection — Dict / List / Set](#5-observablecollection--dict--list--set)
6. [bind_to / bind_from / bind — API](#6-bind_to--bind_from--bind--api)
7. [bindable_dataclass](#7-bindable_dataclass)
8. [Binding Cleanup](#8-binding-cleanup)
9. [Common Issues & Fixes](#9-common-issues--fixes)

---

## 1. Two Types of Bindings

NiceGUI uses **two fundamentally different mechanisms** depending on the source object:

| Mechanism | When used | Update trigger | Source |
|-----------|-----------|----------------|--------|
| `active_links` | Source is NOT a BindableProperty | Polled every `binding_refresh_interval` (default: 0.1s) | `bind_from`, `bind_to` on plain dicts/objects |
| `bindings` dict | Source IS a BindableProperty | Immediate, recursive propagation on `__set__` | `BindableProperty`, `ObservableDict/List` |

**The distinction matters for latency:** plain dict bindings have up to 100ms lag; `BindableProperty` propagates instantly.

---

## 2. active_links — Polled Bindings

```python
# binding.py
active_links: list[tuple[Any, str, Any, str, Callable | None]] = []
# (source_obj, source_name, target_obj, target_name, transform)
```

**Refresh loop** (runs as background task since app startup):

```python
async def refresh_loop():
    await _active_links_added.wait()  # sleeps until first binding added
    while True:
        _refresh_step()
        await asyncio.sleep(core.app.config.binding_refresh_interval)
```

**One step:**
```python
def _refresh_step():
    for source_obj, source_name, target_obj, target_name, transform in active_links:
        if hasattr(source_obj, source_name):
            source_value = getattr(source_obj, source_name)  # or obj[name] for dicts
            value = transform(source_value) if transform else source_value
            if getattr(target_obj, target_name) != value:
                setattr(target_obj, target_name, value)
                _propagate(target_obj, target_name)  # cascade to downstream bindings
```

**Binding from a plain dict (active_link path):**
```python
data = {'count': 0}

# bind_from adds data → label.text to active_links
label.bind_text_from(data, 'count')

# bind_to adds label.text → data to active_links
label.bind_text_to(data, 'count')
```

**active_links are only added if the source is NOT in `bindable_properties`:**
```python
def bind_to(self_obj, self_name, other_obj, other_name, forward=None, ...):
    bindings[(id(self_obj), self_name)].append((self_obj, other_obj, other_name, forward))
    if (id(self_obj), self_name) not in bindable_properties:
        active_links.append((self_obj, self_name, other_obj, other_name, forward))
```

---

## 3. bindings dict — Event-Driven Propagation

```python
# binding.py
bindings: defaultdict[tuple[int, str], list[...]] = defaultdict(list)
# key = (id(source_obj), source_attr_name)
# value = [(source_obj, target_obj, target_name, transform), ...]
```

Propagation is triggered by `_propagate(source_obj, source_name)`:

```python
def _propagate_recursively(source_obj, source_name):
    visited = propagation_visited.get()  # ContextVar — prevents cycles

    if (id(source_obj), source_name) in visited:
        return  # cycle guard
    visited.add((id(source_obj), source_name))

    source_value = getattr(source_obj, source_name)

    for _, target_obj, target_name, transform in bindings.get((id(source_obj), source_name), []):
        target_value = transform(source_value) if transform else source_value
        if getattr(target_obj, target_name) != target_value:
            setattr(target_obj, target_name, target_value)
            _propagate_recursively(target_obj, target_name)  # recurse into downstream
```

**Cycle detection:** uses a `ContextVar[set]` token — the set is per-call, reset after propagation completes.

---

## 4. BindableProperty — Property Descriptor

`BindableProperty` is a Python [descriptor](https://docs.python.org/3/howto/descriptor.html) that triggers immediate propagation on value set:

```python
class BindableProperty:
    def __set_name__(self, owner, name):
        self.name = name

    def __get__(self, owner, _=None):
        return getattr(owner, '___' + self.name)  # private backing attr

    def __set__(self, owner, value):
        has_attr = hasattr(owner, '___' + self.name)
        value_changed = has_attr and getattr(owner, '___' + self.name) != value
        setattr(owner, '___' + self.name, value)

        key = (id(owner), str(self.name))
        bindable_properties[key] = owner  # register as instant-propagation source

        _propagate(owner, self.name)       # immediate cascade

        if value_changed and self._change_handler is not None:
            self._change_handler(owner, value)   # optional side effect
```

**Usage in Timer:**
```python
class Timer:
    active = BindableProperty()   # can bind to this
    interval = BindableProperty() # can bind to this

# Example: bind a checkbox to timer.active
timer = ui.timer(1.0, callback)
checkbox.bind_value(timer, 'active')
```

**Custom BindableProperty with change handler:**
```python
class Model:
    def _on_count_change(self, value):
        print(f'count changed to {value}')

    count = BindableProperty(on_change=_on_count_change)
```

**Important:** BindableProperty stores its value in `___name` (triple underscore prefix) on the instance. Don't use `___` prefixed attributes in your own classes.

---

## 5. ObservableCollection — Dict / List / Set

`ObservableDict`, `ObservableList`, `ObservableSet` are subclasses that fire `_handle_change()` on every mutation:

```python
class ObservableCollection:
    def _handle_change(self):
        self.last_modified = time.time()
        for handler in self.change_handlers:
            events.handle_event(handler, ObservableChangeEventArguments(sender=self))
```

**`change_handlers`** walks up the parent chain:
```python
@property
def change_handlers(self):
    handlers = self._change_handlers[:]
    if self._parent is not None:
        handlers.extend(self._parent.change_handlers)  # bubble up
    return handlers
```

**Nested observables auto-wrap:** when you set a dict/list/set value inside an ObservableDict, it gets wrapped:
```python
data = ObservableDict()
data['nested'] = {'a': 1}     # {'a': 1} becomes ObservableDict
data['nested']['a'] = 2       # triggers data._handle_change()
```

**`app.storage.user`, `app.storage.general`, `app.storage.client`** are all `ObservableDict` (or subclass). Direct mutations trigger `element.update()` if bound.

### Why bind_value works with dicts

```python
ui.input().bind_value(data, 'name')
# Internally calls bind_to + bind_from
# Since data is an ObservableDict (not a plain dict), mutations are instant:
#   data['name'] = 'Alice' → _handle_change() → _propagate → input.value = 'Alice'
```

But plain dicts use `active_links` (polled):
```python
plain = {'name': ''}
ui.input().bind_value(plain, 'name')
# plain['name'] = 'Alice' → seen at next 0.1s tick
```

---

## 6. bind_to / bind_from / bind — API

### bind_to (one-way: self → other)

```python
binding.bind_to(
    self_obj=source,   # object to read from
    self_name='attr',  # attribute to read
    other_obj=target,  # object to write to
    other_name='prop', # attribute to write
    forward=lambda x: x.upper(),  # optional transform
)

# Element convenience methods:
element.bind_text_to(data, 'key')              # bind element.text → data['key']
element.bind_visibility_to(data, 'visible')
element.bind_enabled_to(data, 'enabled')
```

### bind_from (one-way: other → self)

```python
element.bind_text_from(data, 'key')            # data['key'] → element.text
element.bind_text_from(data, 'key', backward=str.upper)
```

### bind (two-way)

```python
element.bind_value(data, 'key')                # element.value ↔ data['key']
element.bind_value(obj, 'attr',
    forward=lambda x: x * 2,
    backward=lambda x: x / 2)
```

**Two-way binding initialization:** backward takes precedence — `other → self` happens first.

### strict mode

```python
# By default, non-dict objects are checked for the attribute (strict=True equivalent)
element.bind_text_from(data, 'missing_key')   # raises KeyError for ObservableDict
element.bind_text_from(data, 'missing_key', other_strict=False)  # lazy: ok
```

---

## 7. bindable_dataclass

Converts a dataclass into one where every field is a `BindableProperty`:

```python
from nicegui.binding import bindable_dataclass, BindableProperty

@bindable_dataclass
class AppState:
    count: int = 0
    name: str = ''
    active: bool = True

state = AppState()

# Now all fields are instantly reactive:
label.bind_text_from(state, 'count')
state.count = 5   # → label immediately updates
```

**Selective fields:**
```python
@bindable_dataclass(bindable_fields=['count'])
class AppState:
    count: int = 0      # BindableProperty — instant
    name: str = ''      # plain field — not reactive
```

**Limitations:** `slots=True` and `frozen=True` are not supported. These conflict with BindableProperty's `__set__` mechanism.

---

## 8. Binding Cleanup

When elements are deleted, their bindings must be removed to prevent memory leaks and stale updates:

```python
# client.py remove_elements()
binding.remove(element_list)

# binding.py remove()
def remove(objects):
    object_ids = set(map(id, objects))
    active_links[:] = [
        link for link in active_links
        if id(link.source_obj) not in object_ids
        and id(link.target_obj) not in object_ids
    ]
    for key, binding_list in list(bindings.items()):
        binding_list[:] = [b for b in binding_list
                          if id(b.source_obj) not in object_ids
                          and id(b.target_obj) not in object_ids]
    for obj_id, name in list(bindable_properties):
        if obj_id in object_ids:
            del bindable_properties[(obj_id, name)]
```

**Implication:** deleting an element auto-removes all its bindings. But bindings from/to external data objects (dicts, custom classes) persist until those objects are GC'd. With `@ui.refreshable`, old elements and their bindings are cleaned up on `.refresh()` call.

---

## 9. Common Issues & Fixes

### Binding not updating

```python
# Problem: plain dict, update happens at next poll (up to 0.1s)
data = {'value': 0}
label.bind_text_from(data, 'value')
data['value'] = 42   # may take up to 0.1s to appear

# Fix 1: use ObservableDict (instant)
data = ObservableDict({'value': 0})

# Fix 2: call _propagate manually (rarely needed)
from nicegui.binding import _propagate
_propagate(data, 'value')

# Fix 3: use BindableProperty on your own class (instant)
class State:
    value = BindableProperty()
state = State()
state.value = 0
label.bind_text_from(state, 'value')
state.value = 42  # instant
```

### Circular binding hangs

Binding A→B and B→A is safe — cycle detection prevents infinite loops:
```python
# Cycle guard uses ContextVar[set] per propagation call
# If (id(obj), attr) is in visited set, stops recursion
```

### "Too many active links" warning

```python
# If active_links grows large:
# 1. binding_refresh_interval=0.1 takes >10ms → warning logged
# 2. Reduce number of polled bindings
# 3. Use BindableProperty sources instead (removed from active_links)
# 4. Increase binding_refresh_interval to reduce CPU
ui.run(binding_refresh_interval=0.5)   # check every 500ms

# Disable entirely if not needed:
ui.run(binding_refresh_interval=None)  # no polling loop
```

### binding_refresh_interval=None

```python
# Disables the active_links polling loop entirely
# All bindings must use BindableProperty or ObservableCollection sources
# Use when: all your reactive state is in ObservableDicts or custom BindableProperty classes
ui.run(binding_refresh_interval=None)
```

### Binding in background tasks

```python
# Problem: _refresh_step runs in event loop, but background thread mutates state
import threading
data = ObservableDict({'value': 0})

def background():
    data['value'] = 42   # triggers _handle_change → _propagate
    # Safe: ObservableDict propagation is asyncio-aware

# If you're in a truly async background task:
async def update():
    data['value'] = 42   # also safe — asyncio context
```
