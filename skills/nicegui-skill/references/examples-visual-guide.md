# NiceGUI Examples Visual Guide

## Purpose
This guide maps each official NiceGUI example to its visual pattern, UI components, and the techniques it demonstrates. Use this when planning UI layouts — find an example that matches the desired UX pattern and reference the corresponding code.

---

## By UI Pattern Category

### Authentication & Login
| Example | Visual | Key Technique |
|---------|--------|--------------|
| `authentication` | Centered login card (username/password fields, LOG IN button) → post-login page ("Hello user1!") | Middleware auth, `app.storage.user`, session redirect |
| `google_oauth2` | Google account chooser dialog | OAuth2 with `authlib`, `RedirectResponse` |
| `google_one_tap_auth` | Floating Google One Tap sign-in popup | Google Identity Services JS integration |
| `descope_auth` | Card with email input, Google/Apple OAuth buttons | Third-party auth provider (Descope) |

### Chat & Messaging
| Example | Visual | Key Technique |
|---------|--------|--------------|
| `chat_app` | Chat bubbles (green sent, gray received), avatars, timestamps, footer input | `Event[str]` broadcast, per-client context, `app.clients()` |
| `chat_with_ai` | Tabbed view (CHAT / LOGS), AI response bubbles | Streaming AI responses, `ui.chat_message`, async generator |

### Data Tables & Grids
| Example | Visual | Key Technique |
|---------|--------|--------------|
| `editable_ag_grid` | AG Grid with Name/Age/Id columns, DELETE SELECTED + NEW ROW buttons, toast notification | `ui.aggrid`, row selection, cell editing, JS-side operations |
| `editable_table` | Simple table with purple ADD ROW button, trash icons per row | `ui.table`, `@ui.refreshable`, dynamic row manipulation |
| `sqlite_database` | Name/Age input fields, table of records, + and trash icons | SQLite CRUD, `aiosqlite`, `@ui.refreshable` |
| `pandas_dataframe` | 4-column numeric table with checkboxes, "Set (2,2) to 0.42" toast | `ui.table` from pandas DataFrame, cell update via `run_row_method` |
| `table_and_slots` | Table with search input, checkboxes, pagination (10 per page), "1-7 of 7" indicator | `ui.table` slots (top-row, bottom-row), search + pagination, row selection |

### Navigation & Layout Templates
| Example | Visual | Key Technique |
|---------|--------|--------------|
| `menu_and_tabs` | Blue header + hamburger → left sidebar, main tabs (A/B/C), blue footer | `ui.header`, `ui.left_drawer`, `ui.tabs`, `ui.footer` |
| `modularization` | Blue header with nav links (Home/A/B/C), centered page title | `APIRouter`, separate page files, shared header component |
| `single_page_app` | Light blue nav tabs (HOME/SECRET/INVALID/ERROR) + LOGOUT button | `ui.sub_pages`, route-based auth guards, tab-driven SPA |

### AI & LLM Integration
| Example | Visual | Key Technique |
|---------|--------|--------------|
| `ai_interface` | Split: left audio transcription panel (Whisper) + right image gen panel (Stable Diffusion), progress bar | Multi-model interface, `run.io_bound`, progress updates |
| `openai_assistant` | Q&A interface, formatted multi-paragraph answer | OpenAI Assistants API, streaming response rendering |

### 3D & Visualization
| Example | Visual | Key Technique |
|---------|--------|--------------|
| `3d_scene` | Full-screen 3D scene with white grid floor, cat character | `ui.scene`, Three.js objects, 3D transforms |
| `svg_clock` | Analog clock face with hour/minute/black hands, red second hand | `ui.svg`, SVG manipulation, timer-driven updates |
| `simpy` | Centered green traffic light indicator + time display | SimPy discrete-event simulation, `ui.timer` |
| `zeromq` | 2D oscillating line chart | `ui.echart`/`ui.plotly`, ZeroMQ subscriber, async message loop |

### Forms & Input
| Example | Visual | Key Technique |
|---------|--------|--------------|
| `todo_list` | "My Weekend" header, tabs (Completed:1 / Remaining:3), checkboxes, trash icons, "New item" input | `@ui.refreshable`, `BindableProperty`, filter with tabs |
| `signature_pad` | Canvas with handwritten "NiceGUI", blue CLEAR button | Custom Vue component, canvas drawing |
| `download_text_as_file` | Text editor area + file save dialog overlay | `ui.download`, save dialog, `ui.textarea` |
| `generate_pdf` | Form (Name/Email inputs), blue PDF button, Save As dialog | `fpdf`, `ui.download`, async PDF generation |
| `search_as_you_type` | Rounded search box with "blue mar" typed, cocktail result card with image | Debounced search, API calls, `@ui.refreshable` results |

### Progress & Background Tasks
| Example | Visual | Key Technique |
|---------|--------|--------------|
| `progress` | Blue COMPUTE button, horizontal progress bar (~42%) | `run.cpu_bound`, `multiprocessing.Value`, timer polling progress |
| `global_worker` | Blue COMPUTE button, progress bar (~45%) | Single global worker thread, `Event[float]` for progress broadcast |
| `ffmpeg_extract_images` | Two progress cards (file select + video upload "devsong.mp4 11.4MB"), spinner | `ui.upload`, ffmpeg subprocess, progress streaming |
| `script_executor` | Three blue script buttons, output text area | Subprocess execution, async stdout streaming, `run.io_bound` |

### Media & Files
| Example | Visual | Key Technique |
|---------|--------|--------------|
| `audio_recorder` | Large red "Hold to Record" button, PLAY + DOWNLOAD buttons below | Custom Vue recorder component, audio blob handling |
| `slideshow` | Full-screen dandelion photo | `ui.image`, timer-driven slide changes |
| `lightbox` | Large image area with loading spinner | Custom lightbox component, click-to-open |
| `opencv_webcam` | Black video feed | `ui.interactive_image`, OpenCV frame capture, base64 stream |
| `image_mask_overlay` | Bear + black mask + masked result (visual equation) | `ui.image`, PIL masking, `app.add_static_file` |
| `infinite_scroll` | Photo grid with blue loading spinners at bottom | JS scroll event, `app.clients()`, lazy image loading |

### External Device & Protocol Integration
| Example | Visual | Key Technique |
|---------|--------|--------------|
| `pyserial` | "Send command" text input | PySerial async read loop, `run.io_bound`, `Event[str]` |
| `webserial` | Blue CONNECT button, LED + Button toggles | WebSerial browser API, JS↔Python bridge |
| `websockets` | Blue SEND HELLO button, connection count + message | `ui.on('websocket_message')`, native WebSocket handler |
| `xterm` | Full black terminal with bash shell | `ui.terminal`, xterm.js, subprocess PTY |
| `ros2` | Three-panel: joystick Control + Data sliders (velocity/position) + 3D Visualization | ROS2 pub/sub, `ui.joystick`, `ui.scene` |

### Architecture & Patterns
| Example | Visual | Key Technique |
|---------|--------|--------------|
| `fastapi` (1) | JSON viewer with "pretty print" checkbox | FastAPI + NiceGUI side-by-side on same process |
| `fastapi` (2) | Dark mode text display ("Hello, NiceGUI!") + dark mode checkbox | `ui.run_with(fastapi_app)`, dark mode toggle |
| `threaded_nicegui` | "NiceGUI running in separate thread" text | `threading.Thread`, `ui.run()`in non-main thread |
| `redis_storage` | Three-tab interface (general/user/tab) | Redis as persistent backend for `app.storage` |

### Infrastructure Demos
| Example | Visual | Key Technique |
|---------|--------|--------------|
| `docker_image` | Simple text display with persistence message | Production `ui.run()` settings, Docker volume patterns |
| `nginx_https` | "Hello HTTPS encrypted world" | Nginx SSL termination, WebSocket proxy |
| `nginx_subpath` | "This is a subpage" + BACK button | `uvicorn_kwargs={'root_path': '/myapp'}`, nginx subpath |

### Payments & Third-Party Services
| Example | Visual | Key Technique |
|---------|--------|--------------|
| `stripe` | "Buy a Product" heading, blue CHECKOUT button | Stripe Checkout, redirect to payment page |

### Custom Components & JS Integration
| Example | Visual | Key Technique |
|---------|--------|--------------|
| `custom_vue_component` | Green "Count: 3" box + orange "State: ON" box, RESET buttons, toast "value changed to True" | Vue SFC, `ui.element` subclass, custom events |
| `vue_vite` | Green "Options: 1" + "Composition: 2" boxes, RESET buttons | Vue Composition API, Vite build, module imports |
| `node_module_integration` | Large "42" text + CHECK button + "42 is even" notification | npm package in browser, `ui.add_body_html` |
| `slots` | Nested collapsible list with icons and share buttons | `ui.element` slot injection, `ui.item`, `ui.expansion` |
| `table_and_slots` | Search + paginated table | `ui.table` with custom slot templates |
| `custom_binding` | Colored weather buttons (Berlin 22°C, New York 13°C, Tokyo 20°C) | `BindableProperty`, custom getter/setter binding |

### Calendar & Scheduling
| Example | Visual | Key Technique |
|---------|--------|--------------|
| `fullcalendar` | September 2025 month calendar, colored event dots (Math/Physics/Chemistry), sidebar legend | FullCalendar.js integration, JS event bridge |

### Kanban & Project Management
| Example | Visual | Key Technique |
|---------|--------|--------------|
| `trello_cards` | Kanban board: "Next", "Doing", "Done" columns, white draggable cards | `Sortable.js`, drag-drop via JS, `app.storage.general` |

### Testing
| Example | Visual | Key Technique |
|---------|--------|--------------|
| `pytests` | "Try running pytest on this project!" + CLICK ME button + subpage link | `Screen`/`User` test fixtures, `pytest-nicegui` |

---

## Component Usage Reference

### When to use what table component
| Need | Component | Example |
|------|-----------|---------|
| Simple CRUD list | `ui.table` + `@ui.refreshable` | `sqlite_database`, `editable_table` |
| Excel-like editing | `ui.aggrid` | `editable_ag_grid` |
| Search + pagination | `ui.table` with slots | `table_and_slots` |
| Pandas data | `ui.table(rows=df.to_dict('records'))` | `pandas_dataframe` |

### When to use what layout pattern
| Need | Pattern | Example |
|------|---------|---------|
| Header + drawer + tabs | `ui.header` + `ui.left_drawer` + `ui.tabs` | `menu_and_tabs` |
| Multi-page SPA with auth | `ui.sub_pages` + route guards | `single_page_app` |
| Modular pages | `APIRouter` + separate files | `modularization` |
| Kanban/drag-drop | Sortable.js custom component | `trello_cards` |

### When to use what broadcast pattern
| Need | Pattern | Example |
|------|---------|---------|
| Push to ALL clients | `Event[T]` emit | `chat_app`, `global_worker` |
| Push to specific page | `app.clients('/path')` + `with client:` | `chat_app`, `redis_storage` |
| Per-tab state | `app.storage.tab` | `redis_storage` |
| Cross-tab user state | `app.storage.user` | `authentication`, `sqlite_database` |

---

## Visual Complexity Reference

### Simple (≤3 components, minimal state)
- `api_requests` — button + label
- `download_text_as_file` — textarea + button + dialog
- `nginx_https` / `nginx_subpath` — text display + button
- `stripe` — heading + checkout button
- `threaded_nicegui` — text display
- `simpy` — label + colored indicator + timer

### Medium (form + data + navigation)
- `todo_list` — tabs + checklist + input
- `sqlite_database` — form + table + CRUD
- `search_as_you_type` — search + results
- `progress` / `global_worker` — button + progress bar
- `script_executor` — buttons + output stream
- `signature_pad` — canvas + clear button

### Complex (multiple panels, real-time, auth)
- `chat_app` — real-time multi-user chat with sidebar
- `authentication` — full auth flow with session management
- `menu_and_tabs` — full layout template
- `trello_cards` — Kanban with drag-drop
- `ros2` — three-panel control/data/visualization
- `ai_interface` — dual AI model interface
- `fullcalendar` — interactive calendar with events
