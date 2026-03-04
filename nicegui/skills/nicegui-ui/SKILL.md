---
name: nicegui-ui
description: Build, update, or adjust any UI, frontend, component, page, or site using NiceGUI or Python. Trigger on: NiceGUI app, Python UI, dashboard, form, component, auth, FastAPI frontend, table, chat app, real-time UI, header/footer/sidebar, dockerize app, or any frontend/UI work in a Python project.
version: 0.5.0
---

# NiceGUI UI Skill

NiceGUI builds web UIs in Python — wraps Quasar (Vue 3), uses FastAPI internally, communicates via WebSocket. Every `@ui.page()` call is fresh per client.

```
Read references/quick-patterns.md for code snippets (frame, refreshable, dialog, async load, colors, structure).
```

## Phase 0: Project Scan (ALWAYS FIRST)

Before writing any code, scan the project:

1. List root files — find `main.py`, `requirements.txt`, `pyproject.toml`, `Dockerfile`, API files
2. Check for existing NiceGUI patterns — `ui.run()`, `@ui.page()`, `components/`, `pages/`
3. Look for existing API (`app.py`, `api/`, `routers/`, FastAPI routes)
4. Check styling — existing `ui.colors()`, Tailwind config
5. Identify data models — DB models, Pydantic schemas

Output a brief summary. Never assume — always check first.

```
Read references/project-setup.md for full scanning protocol and bootstrap templates.
```

---

## Phase 1: UX Consultation

Act as a professional UI/UX developer. Ask targeted questions — only what you can't infer.

**Must-ask (if not inferable):**
- Primary purpose? (data entry / monitoring / content / workflow)
- Users? (internal / public / mobile / desktop)
- Navigation model? (single-page / multi-page / tabs / sidebar)

**Infer without asking when:**
- Project has existing pages/routes → continue its nav pattern
- Existing colors/theme → continue it
- Surgical request ("add a button") → don't redesign

Present a short ASCII wireframe before building any new layout.

```
Read references/ux-consultation.md for consultation workflow and layout patterns.
```

---

## Phase 1.5: Design Direction → Theme Contract

After understanding the UX structure, commit to a **bold aesthetic direction** and encode all visual decisions into a single `setup_theme()` function. This function is the **contract** between design and implementation — all subsequent component code references it semantically, never with raw values.

**Step 1 — Pick ONE aesthetic and execute it with precision:**
- Brutally minimal · Maximalist/layered · Retro-futuristic · Organic/natural
- Luxury/refined · Playful/toy-like · Editorial/magazine · Industrial/utilitarian
- Art deco/geometric · Soft/pastel · Brutalist/raw · Dark-glass/glassmorphism

Decide: What tone fits the user? Light or dark? What makes this UNFORGETTABLE?

**Step 2 — Produce a `setup_theme()` function.** This is the only place raw hex values or font names appear in the entire codebase:

```python
def setup_theme():
    ui.add_head_html('...')       # Google Fonts + global body/heading selectors
    ui.colors(primary=..., secondary=..., accent=..., positive=..., negative=...)
    ui.add_css(':root { --bg: ...; --surface: ...; --border: ...; }')
    ui.add_css('...')             # page background, animations, component overrides
```

Call `setup_theme()` once at app startup. Phase 2 component code only ever references the semantic tokens it establishes (`text-primary`, `var(--surface)`, `.props('color=accent')`).

**NEVER produce generic AI aesthetics:**
- No Inter/Roboto/Arial as primary font — always load a distinctive Google Font pair
- No `ui.colors(primary='#1565C0')` by default — pick something specific to this app
- No purple gradients on white — choose a palette that fits the context
- No timid, evenly-distributed palettes — dominant color with sharp accents

```
Read references/design-aesthetics.md for aesthetic direction guide, font pairs,
color strategies, animation patterns, and complete setup_theme() recipes.
```

---

## Phase 2: Standards

**Component rules:**
- Components used in 2+ places → `components/`
- Use `@contextmanager` for layout wrappers
- Use `@ui.refreshable` for any content that changes after load
- Mark elements with `.mark('name')` for testability

**Styling rules — reference the theme, never redefine it:**
- **Colors**: use semantic names from `ui.colors()` (`text-primary`, `.props('color=primary')`) or CSS vars from `setup_theme()` (`var(--surface)`) — raw hex only inside `setup_theme()`
- **Fonts**: Tailwind classes for scale (`text-sm`, `text-xl font-bold`); font families already set globally by `setup_theme()`
- **Spacing**: use inline `style('gap: 1rem')` / `style('gap: 0.5rem')` — **not** `gap-*` Tailwind classes (unreliable inside Quasar flex containers); `p-4`/`p-6` padding is fine
- **Width**: always `max-w-*` + `mx-auto` — never unbounded columns
- **`element.style()`**: only for values Tailwind/props can't express (gradients, custom shadows, extreme letter-spacing)

**NiceGUI layout gotchas:**
- `height: 100%` inside a `max-height` container collapses — use `min-height` or fixed height instead
- Side-by-side flex children need `style('min-width: 0')` to prevent overflow
- `table-layout: fixed` with percentage widths in `ui.html()` tables breaks — use absolute widths or let the browser size columns
- Modal action buttons must be docked (always visible, not scrolled away with content)

---

## Phase 3: API Integration

**Existing API:** Check if NiceGUI wraps the same FastAPI instance (`ui.run_with(app)`). Add pages without touching API routes.

**No existing API:** NiceGUI's built-in `app` is the API. Add `@app.get/post()` alongside `@ui.page()`. Keep pages thin — data in `services/`.

```
Read references/integrations.md for full integration patterns.
Read references/architecture.md for APIRouter and modular layouts.
```

---

## Phase 4: Performance

- Use `@ui.refreshable` + `.refresh()` — don't rebuild the whole page
- Surgical updates (`label.text = x`) beat full refreshes
- Timer intervals ≥ 1s; use `Event[T]` push instead of polling
- Batch data fetches — one async call per page load, not per widget
- Serve static files via `app.add_static_files()`, not base64
- Heavy work → `run.cpu_bound()` / `run.io_bound()` — never block event loop

```
Read references/performance.md for detailed optimization guide.
```

---

## Build Checklist

Run through the relevant sections before delivering any non-trivial page or component.

### Data Display Components
When the same data appears in multiple places (list row, detail view, modal, search result):
- [ ] Listed ALL locations where this data appears in the app
- [ ] Component has modes for each context (compact / full / inline)
- [ ] User can navigate from a reference to the source (e.g. list row → detail page)
- [ ] Same icon, typography, and color coding used in every context
- [ ] Actions scoped to context (e.g. edit only in detail/library view, not in reference chips)

### UI Architecture
- [ ] Business logic in a controller or service, not inside UI event handlers
- [ ] Data fetching returns Pydantic models, not raw dicts
- [ ] All user actions logged at the start of their handlers (before async work)
- [ ] UI gives feedback when an action is deferred or blocked (spinner, notify, disabled state)
- [ ] No implicit boolean flags for state — use enums or explicit state objects
- [ ] Controller logic covered by integration tests (not just UI tests)

### NiceGUI Styling
- [ ] No `gap-*` Tailwind classes — spacing uses `style('gap: ...')`
- [ ] No `height: 100%` inside a `max-height` container
- [ ] No `table-layout: fixed` with percentage widths inside `ui.html()` tables
- [ ] Side-by-side flex children have `style('min-width: 0')`
- [ ] Modal / dialog action buttons are docked (always visible, not scrollable)

---

## Reference Files

### Standard
| File | Load when |
|------|-----------|
| `references/quick-patterns.md` | Need code snippets — frame, refreshable, dialog, async, colors |
| `references/project-setup.md` | Scanning a project, creating structure |
| `references/ux-consultation.md` | Layout planning, UX questions, wireframes |
| `references/design-aesthetics.md` | Choosing aesthetic direction, fonts, colors, animations, backgrounds |
| `references/components.md` | Full component API — all `ui.*` elements |
| `references/layouts-and-styling.md` | Tailwind, theming, dark mode, CSS injection |
| `references/async-and-events.md` | Async lifecycle, `Event[T]`, timers, streaming |
| `references/data-binding.md` | `bind_value`, `@ui.refreshable`, `BindableProperty` |
| `references/auth-and-storage.md` | Middleware auth, OAuth2, session storage |
| `references/integrations.md` | FastAPI, DB, WebSockets, Redis, external APIs |
| `references/custom-components.md` | Vue SFCs, element subclassing, drag-drop |
| `references/architecture.md` | APIRouter, modular pages, multi-client sync |
| `references/performance.md` | Network optimization, render efficiency, caching |
| `references/docker.md` | Docker builds, docker-compose, deployment |
| `references/testing.md` | pytest Screen/User fixtures, marks, multi-user |
| `references/lifecycle-and-internals.md` | Storage tiers, client lifecycle, page rendering |
| `references/examples-visual-guide.md` | Visual map of all 55 examples by UI pattern |

### Deep Internals (debugging & complex scenarios)
> Load only the file matching the issue — each is self-contained.

| File | Load when |
|------|-----------|
| `references/internals-element.md` | Subclassing Element, missing updates, slot stack errors, deletion |
| `references/internals-rendering.md` | WebSocket flow, Outbox batching, reconnect/rewind, render perf |
| `references/internals-binding.md` | Binding not updating, `BindableProperty`, `ObservableCollection` internals |
| `references/internals-events.md` | Custom events, `EventListener` throttle, `Event[T]` internals, JS bridge |
| `references/internals-routing.md` | Page decorator, `response_timeout`, sub_pages, `APIRouter`, `ui.run()` params |

## Example Apps

| File | What it shows |
|------|--------------|
| `examples/basic_app.py` | Full app shell — header/drawer/tabs/cards/dialogs |
| `examples/auth_app.py` | Middleware auth, login/logout, roles, per-user prefs |
| `examples/crud_table.py` | Add/edit/delete with dialogs, filters, ag-grid |
| `examples/chat_app.py` | Real-time multi-user chat with `Event[T]` |

```bash
pip install nicegui && python main.py   # dev
```
For Docker: `read references/docker.md`
