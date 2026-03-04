# NiceGUI UX Consultation Reference

## Table of Contents
1. [When to Ask vs When to Infer](#1-when-to-ask-vs-when-to-infer)
2. [Discovery Questions by App Type](#2-discovery-questions-by-app-type)
3. [Header Patterns](#3-header-patterns)
4. [Navigation Patterns](#4-navigation-patterns)
5. [Layout Archetypes](#5-layout-archetypes)
6. [Footer Patterns](#6-footer-patterns)
7. [Color Palette Selection](#7-color-palette-selection)
8. [Component Design Decisions](#8-component-design-decisions)
9. [Wireframe Notation](#9-wireframe-notation)
10. [UX Standards Checklist](#10-ux-standards-checklist)

---

## 1. When to Ask vs When to Infer

### Ask when:
- Starting a new project with no existing structure
- Adding a major new section/page to an existing app
- Choosing between fundamentally different layouts (e.g., sidebar vs. top-nav)
- Colors and branding are not established
- The target user or device is unclear

### Infer without asking when:
- The project already has a `components/frame.py` — use that pattern
- Existing `ui.colors()` sets the palette — match it
- Adding a CRUD table → follow the existing table style in the project
- Small surgical changes ("add a refresh button") → don't redesign

### Limit questions to 3 or fewer per interaction
Pick the highest-impact questions. Present options with brief explanations, not open-ended blanks.

---

## 2. Discovery Questions by App Type

### For a new app (no existing structure):
```
1. What does this app primarily do?
   a) Data monitoring/dashboard (read-heavy)
   b) Data entry / workflow (write-heavy)
   c) Content/document viewer
   d) Tool / utility

2. Who uses it?
   a) Internal team (trusted, feature-rich OK)
   b) Public users (need simpler, more polish)
   c) Admins only

3. Primary device?
   a) Desktop/laptop (can use sidebars, dense layouts)
   b) Mobile/tablet (need responsive, touch-friendly)
   c) Both
```

### For adding a feature:
```
1. Does this feature need its own page or live on an existing page?
2. Is this accessible to all users or specific roles?
3. Does it show data, collect data, or both?
```

### For styling/branding:
```
1. Do you have brand colors? (provide hex values)
   If not → suggest a palette based on app purpose
2. Tone: professional/corporate, friendly/modern, minimal/clean, bold/energetic?
3. Dark mode: optional, always-on, or never?
```

---

## 3. Header Patterns

### Pattern A — Full App Header (most common)
Use for: Multi-page apps with persistent nav, user session.

```
┌─────────────────────────────────────────────────────────┐
│ ☰  AppName           ┄┄┄ search ┄┄┄      👤 Alice  ⋮  │
└─────────────────────────────────────────────────────────┘
```

```python
with ui.header(elevated=True).classes('bg-primary text-white items-center px-6 h-14 gap-3'):
    ui.button(icon='menu', on_click=drawer.toggle).props('flat round color=white')
    ui.label('AppName').classes('text-xl font-bold')
    ui.space()
    search = ui.input(placeholder='Search...').props('dense standout dark')  # optional
    ui.space()
    ui.label(username).classes('text-sm opacity-80')
    ui.button(icon='more_vert').props('flat round color=white')
```

### Pattern B — Minimal Header (tools, utilities)
Use for: Single-purpose tools, data views without user sessions.

```
┌─────────────────────────────────────────────────────────┐
│  AppName / Page Title                          Actions  │
└─────────────────────────────────────────────────────────┘
```

```python
with ui.header().classes('bg-white border-b text-grey-9 items-center px-6 h-12 gap-3'):
    ui.label('AppName').classes('text-lg font-semibold text-primary')
    ui.label('/').classes('text-grey-4')
    ui.label(page_title).classes('text-lg font-medium')
    ui.space()
    # action buttons
```

### Pattern C — Tab Header (section navigation)
Use for: Apps with 3–6 peer sections (no sidebar needed).

```
┌─────────────────────────────────────────────────────────┐
│ AppName            Overview | Data | Settings | Users  │
└─────────────────────────────────────────────────────────┘
```

```python
with ui.header(elevated=True).classes('bg-primary text-white items-center px-6 h-14'):
    ui.label('AppName').classes('text-xl font-bold mr-8')
    with ui.tabs().props('active-color=white indicator-color=white dense').classes('flex-1'):
        ui.tab('overview', label='Overview')
        ui.tab('data', label='Data')
        ui.tab('settings', label='Settings')
    ui.space()
    ui.label(username).classes('text-sm opacity-80')
```

### Pattern D — No Header (single-page utility, kiosk)
Use for: Full-screen dashboards, embedded views, kiosk displays.

```
No header — content fills viewport.
Use ui.query('.nicegui-content').classes('p-0') to remove padding.
```

---

## 4. Navigation Patterns

### Sidebar Drawer (recommended for 5+ sections)
```
┌──────┬────────────────────────────────────┐
│  Nav │  Content                           │
│ Home │                                    │
│ Data │                                    │
│ Rpts │                                    │
│ Sett │                                    │
└──────┴────────────────────────────────────┘
```

```python
with ui.left_drawer(value=True, bottom_corner=True).classes('bg-white border-r w-56'):
    with ui.column().classes('w-full px-3 pt-4 gap-1'):
        for route, icon, label in NAV_ITEMS:
            active = current_route == route
            with ui.item(on_click=lambda r=route: ui.navigate.to(r)).classes(
                'rounded-lg ' + ('bg-primary/10 text-primary' if active else 'hover:bg-grey-1')
            ):
                with ui.item_section().props('avatar'):
                    ui.icon(icon, color='primary' if active else 'grey-6')
                with ui.item_section():
                    ui.item_label(label)
```

### Top Navigation (3–5 sections, no drawer)
```
┌─────────────────────────────────────────────────────────┐
│ AppName   [Home]  [Data]  [Reports]  [Settings]   👤   │
└─────────────────────────────────────────────────────────┘
```

```python
with ui.header(elevated=True).classes('bg-primary text-white items-center px-6 h-14 gap-6'):
    ui.label('AppName').classes('text-xl font-bold mr-4')
    for route, label in [('/', 'Home'), ('/data', 'Data'), ('/reports', 'Reports')]:
        active = current_route == route
        ui.button(label, on_click=lambda r=route: ui.navigate.to(r)).props(
            f'flat no-caps color={"white" if active else "white"}'
        ).classes('opacity-100' if active else 'opacity-60 hover:opacity-90')
    ui.space()
    ui.label(username).classes('text-sm')
```

### Tabs-in-page (sub-sections within a page)
```
Content area:
  [Tab A]  [Tab B]  [Tab C]
  ─────────────────────────
  Panel content
```

```python
with ui.tabs().classes('w-full border-b') as tabs:
    ui.tab('a', label='Overview', icon='dashboard')
    ui.tab('b', label='History', icon='history')
    ui.tab('c', label='Settings', icon='tune')

with ui.tab_panels(tabs, value='a').classes('w-full'):
    with ui.tab_panel('a'):
        overview_content()
    with ui.tab_panel('b'):
        history_content()
    with ui.tab_panel('c'):
        settings_content()
```

### Breadcrumbs (hierarchical content)
```
Home › Users › Alice › Edit
```

```python
with ui.breadcrumbs().classes('text-sm mb-4'):
    ui.breadcrumb_el('Home', icon='home', href='/')
    ui.breadcrumb_el('Users', href='/users')
    ui.breadcrumb_el('Alice', href='/users/alice')
    ui.breadcrumb_el('Edit')
```

---

## 5. Layout Archetypes

### Dashboard Layout (metrics + tables/charts)
```
┌───────────────────────────────────────────────────┐
│ [KPI Card]  [KPI Card]  [KPI Card]  [KPI Card]   │
├──────────────────────────┬────────────────────────┤
│                          │  Recent Activity       │
│  Main Chart / Table      │  ──────────────────    │
│                          │  Item 1                │
│                          │  Item 2                │
└──────────────────────────┴────────────────────────┘
```

```python
# KPI row
with ui.grid(columns=4).classes('w-full gap-4'):
    for metric in metrics:
        kpi_card(metric)

# Main + sidebar split
with ui.row().classes('w-full gap-4 items-start'):
    with ui.card().classes('flex-1 p-4'):
        main_chart()
    with ui.card().classes('w-72 shrink-0 p-4'):
        activity_feed()
```

### Form Layout (data entry)
```
┌──────────────────────────────────────┐
│  Section Title                       │
│  ─────────────────                   │
│  Name: [________________]            │
│  Email: [_______________]            │
│  Role:  [▾ Select      ]            │
│                                      │
│  Section 2                           │
│  ─────────────────                   │
│  Option A  ○  Option B  ○           │
│                                      │
│  [Cancel]           [Save Changes]   │
└──────────────────────────────────────┘
```

```python
with ui.card().classes('w-full max-w-2xl p-8'):
    form_section('Personal Info')
    ui.input('Full Name').classes('w-full')
    ui.input('Email').props('type=email').classes('w-full')
    ui.select(roles, label='Role').classes('w-full')

    ui.separator().classes('my-4')
    form_section('Preferences')
    ui.radio(['Option A', 'Option B'], value='Option A').props('inline')

    with ui.row().classes('w-full justify-end gap-3 mt-6'):
        ui.button('Cancel', on_click=cancel).props('flat no-caps')
        ui.button('Save', icon='save', on_click=save).props('color=primary no-caps')
```

### List + Detail (master-detail)
```
┌──────────────────┬───────────────────────────────┐
│ Search [______]  │  Selected Item Detail          │
│ ──────────────   │  ─────────────────────────     │
│ ▸ Item 1         │  Name: Alice Johnson           │
│   Item 2         │  Email: alice@...              │
│   Item 3         │  Status: ● Active              │
│                  │                                │
│                  │  [Edit]  [Delete]              │
└──────────────────┴───────────────────────────────┘
```

```python
with ui.row().classes('w-full h-screen gap-0'):
    # List panel
    with ui.column().classes('w-80 shrink-0 border-r h-full bg-white'):
        ui.input(placeholder='Search...').props('dense outlined').classes('m-3 w-auto')
        with ui.scroll_area().classes('flex-1'):
            item_list()

    # Detail panel
    with ui.column().classes('flex-1 p-6 gap-4'):
        detail_panel()
```

### Full-screen Tool (no nav)
```
┌─────────────────────────────────────────────────────────┐
│  Toolbar: [Action] [Action]          [Save] [Export]   │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Main work area (canvas, editor, viewer)                │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

```python
ui.query('.nicegui-content').classes('p-0 overflow-hidden')

with ui.column().classes('w-full h-screen gap-0'):
    with ui.row().classes('w-full items-center px-4 py-2 border-b bg-white gap-2 shrink-0'):
        toolbar_buttons()
        ui.space()
        ui.button('Save', icon='save').props('color=primary no-caps')
        ui.button('Export', icon='download').props('outline no-caps')

    with ui.column().classes('flex-1 overflow-hidden'):
        main_workspace()
```

---

## 6. Footer Patterns

### Pattern A — Status Footer (always visible)
Use for: Apps that show system status, version, last sync time.

```
┌─────────────────────────────────────────────────────────┐
│  © 2024 AppName   v1.2.0   Last sync: 2 min ago  ● OK │
└─────────────────────────────────────────────────────────┘
```

```python
with ui.footer().classes('bg-grey-1 border-t px-6 py-2 items-center gap-4'):
    ui.label('© 2024 AppName').classes('text-xs text-grey-5')
    ui.space()
    ui.label('v1.2.0').classes('text-xs text-grey-4')
    with ui.row().classes('items-center gap-1'):
        ui.icon('circle').classes('text-green-500 text-xs')
        ui.label('System OK').classes('text-xs text-grey-6')
```

### Pattern B — Action Footer (form submit zone)
Use for: Wizards, multi-step forms, editors with persistent save.

```
┌─────────────────────────────────────────────────────────┐
│  Step 2 of 4                [Back]         [Continue]  │
└─────────────────────────────────────────────────────────┘
```

```python
with ui.footer().classes('bg-white border-t px-6 py-3 items-center'):
    ui.label(f'Step {step} of {total}').classes('text-sm text-grey-6')
    ui.space()
    ui.button('Back', icon='arrow_back', on_click=prev_step).props('flat no-caps')
    ui.button('Continue', icon='arrow_forward', on_click=next_step).props('color=primary no-caps')
```

### Pattern C — No footer (dashboards, tools)
Default. Don't add a footer unless there's a real use for it.

---

## 7. Color Palette Selection

### Suggest based on app purpose:

| App Type | Primary | Secondary | Accent |
|----------|---------|-----------|--------|
| Business/Enterprise | `#1565C0` (blue) | `#00897B` (teal) | `#F57C00` (orange) |
| Healthcare | `#00695C` (teal) | `#1565C0` (blue) | `#E53935` (red for alerts) |
| Finance | `#1A237E` (dark blue) | `#37474F` (grey) | `#4CAF50` (green for positive) |
| Productivity/Tool | `#4527A0` (purple) | `#00897B` (teal) | `#F57C00` (orange) |
| Monitoring/Ops | `#212121` (dark) | `#0D47A1` (blue) | `#F44336` (red for alerts) |
| Creative/Content | `#880E4F` (magenta) | `#4527A0` (purple) | `#FFD600` (yellow) |

```python
# Apply chosen palette
ui.colors(
    primary=PRIMARY,
    secondary=SECONDARY,
    accent=ACCENT,
    positive='#2E7D32',
    negative='#C62828',
    info='#0277BD',
    warning='#E65100',
)
```

### Dark mode considerations
- Always test contrast in both light and dark modes
- Use `dark:text-white dark:bg-grey-9` Tailwind dark variants for custom colors
- Offer dark mode toggle if users will use the app for extended periods

---

## 8. Component Design Decisions

### Cards vs. Table rows
| Use cards when | Use table rows when |
|----------------|---------------------|
| Each item has many fields to show | Comparing across many rows |
| Items have preview images | Need sorting/filtering/pagination |
| ≤ 20 items | 20+ items |
| User needs to act on individual items | User mostly reads/exports |

### Inline edit vs. Dialog edit
| Inline | Dialog |
|--------|--------|
| 1–2 fields | 3+ fields |
| Simple text / numbers | Complex forms with validation |
| Frequent small edits | Intentional actions |
| AG Grid | Standard table |

### Notification placement
- `ui.notify()` — temporary feedback (success, error after action)
- `ui.dialog()` — blocking confirmation (destructive actions, input needed)
- Inline error label — form field validation
- Toast with `position='top'` — critical system alerts

### Loading states
- `ui.spinner()` inline — small section loading
- Full-page spinner with `absolute-center` — initial page load
- `button.props('loading')` — async button action
- `ui.linear_progress()` — file upload, multi-step progress

---

## 9. Wireframe Notation

Use ASCII wireframes to confirm layout before coding. Keep them simple:

```
Legend:
  [Button]       = ui.button
  [____________] = ui.input
  [▾ Select  ]  = ui.select
  ●              = ui.radio / selected state
  ☐              = ui.checkbox
  ───────────    = ui.separator
  │              = column border
  ┌┐ └┘ ├┤ ┬┴  = layout containers
  ┄┄┄            = flexible space (ui.space)
```

Example:
```
┌──── Header ───────────────────────────────────────────┐
│ ☰  Dashboard  ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄   🔔 👤 Alice  ⋮  │
└────────────────────────────────────────────────────────┘
│                                                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐           │
│  │ 1,234    │  │ $45.2k   │  │  98.2%   │           │
│  │ Users    │  │ Revenue  │  │ Uptime   │           │
│  └──────────┘  └──────────┘  └──────────┘           │
│                                                        │
│  ┌─── Recent Orders ─────────┐ ┌── Activity ────────┐│
│  │ Name   Status  Amount     │ │ Alice created order ││
│  │ ─────  ──────  ──────     │ │ Bob updated status  ││
│  │ Alice  ● Done  $120       │ │ System backup OK    ││
│  │ Bob    ○ Pend  $89        │ │                     ││
│  └───────────────────────────┘ └────────────────────┘│
```

Present the wireframe, ask for confirmation or adjustments, then code.

---

## 10. UX Standards Checklist

Before delivering any new page or component:

**Accessibility**
- [ ] Interactive elements have hover states
- [ ] Destructive actions (delete) require confirmation
- [ ] Error messages are visible inline, not just via notify
- [ ] Keyboard accessible (tab order, enter submits forms)

**Responsiveness**
- [ ] Content has `max-w-*` constraints (not unbounded)
- [ ] No hardcoded pixel widths on flex containers
- [ ] Tables use `pagination` for large datasets

**Consistency**
- [ ] Uses `app_frame()` — not a custom header per-page
- [ ] Same spacing scale: `gap-2` within groups, `gap-4` between sections, `gap-6` between cards
- [ ] Loading states present for async operations
- [ ] Empty states present for zero-data lists

**Performance**
- [ ] Lists use `@ui.refreshable` not full page rebuild
- [ ] No blocking calls in page functions (uses `run.io_bound`)
- [ ] Large datasets paginated (not all loaded at once)

**Code quality**
- [ ] Components placed in `components/` if used 2+ times
- [ ] Page logic in `pages/`, not inline in route decorator
- [ ] Colors come from `ui.colors()`, not hardcoded hex in classes
