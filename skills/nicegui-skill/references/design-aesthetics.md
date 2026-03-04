# NiceGUI Design Aesthetics Reference

Distinctive visual design for NiceGUI apps — applied through NiceGUI's own APIs, not around them.

## How Design and Implementation Collaborate

Design decisions and technical implementation are **not separate tracks**. They integrate through a single contract:

```
Phase 1.5 (Design)     →  setup_theme()  →  Phase 2+ (Implementation)
  Choose aesthetic            │                  Use semantic tokens
  Pick fonts                  │                  text-primary, var(--surface)
  Choose palette              │                  .props('color=accent')
  Define animations           │                  .classes('anim-in')
```

**The rule**: all raw values (hex colors, font names, keyframe definitions) live **only** inside `setup_theme()`. Component code downstream uses only semantic references that `setup_theme()` established. This means:
- Design can evolve by changing one function
- NiceGUI component code stays clean and consistent with Phase 2 standards
- `ui.colors()` is still the single source of truth for Quasar component colors

```python
# setup_theme() — ALL aesthetic decisions live here
def setup_theme():
    # 1. Fonts: loaded once, applied globally via CSS selectors
    ui.add_head_html('''
        <link href="https://fonts.googleapis.com/css2?family=...&display=swap" rel="stylesheet">
        <style>
            body, .q-app { font-family: 'BodyFont', sans-serif; }
            .display      { font-family: 'DisplayFont', serif; }
        </style>
    ''')

    # 2. Quasar semantic palette — component code uses these names, not hex
    ui.colors(
        primary='#...',    # buttons, links, active states
        secondary='#...',  # secondary actions, badges
        accent='#...',     # highlights, focus rings
        positive='#...',   # success states
        negative='#...',   # error states
        info='#...',
        warning='#...',
    )

    # 3. CSS vars for values beyond ui.colors() scope
    ui.add_css('''
        :root {
            --bg: #...;          /* page background */
            --surface: #...;     /* card/panel background */
            --border: #...;      /* dividers, outlines */
            --muted: #...;       /* secondary text */
            --accent-glow: ...;  /* glow effects */
        }
    ''')

    # 4. Global styles: page bg, animations, component class overrides
    ui.add_css('''
        .nicegui-content { background: var(--bg); min-height: 100vh; }
        @keyframes fadeUp { from { opacity: 0; transform: translateY(14px); } to { opacity: 1; } }
        .anim-in { animation: fadeUp 0.45s cubic-bezier(0.22,1,0.36,1) both; }
        /* ... */
    ''')


# Component code — only semantic references, no raw values
def dashboard_card(title, value):
    with ui.card().classes('surface anim-in').style('background: var(--surface); border: 1px solid var(--border)'):
        ui.label(title).classes('text-xs uppercase tracking-widest text-grey-5')
        ui.label(value).classes('text-4xl font-bold text-primary')  # text-primary from ui.colors()
```

---

## Table of Contents
1. [Aesthetic Direction](#1-aesthetic-direction)
2. [Typography](#2-typography)
3. [Color Strategy](#3-color-strategy)
4. [Motion & Animation](#4-motion--animation)
5. [Spatial Composition](#5-spatial-composition)
6. [Backgrounds & Visual Depth](#6-backgrounds--visual-depth)
7. [Anti-Patterns](#7-anti-patterns)
8. [Complete setup_theme() Recipes](#8-complete-setup_theme-recipes)

---

## 1. Aesthetic Direction

Pick ONE clear aesthetic and execute it with precision. Vary between light and dark themes across projects.

| Direction | Characteristics | Works for |
|-----------|----------------|-----------|
| **Brutally Minimal** | Maximum whitespace, one accent color, monospace type | Dev tools, CLIs, utilities |
| **Dark Glass** | Dark base, blur/transparency layers, bright accents | Monitoring, ops dashboards |
| **Editorial** | Large type, asymmetric grid, unexpected whitespace | Content, reports, marketing |
| **Luxury / Refined** | Serif fonts, gold/cream palette, subtle gradients | Finance, premium products |
| **Industrial / Utilitarian** | Dense layouts, clipped corners, warning colors | Data-heavy ops, factories |
| **Retro-Futuristic** | Monospace, scanlines, phosphor green/amber | Terminals, hacker tools |
| **Organic / Natural** | Curved shapes, earth tones, soft shadows | Health, wellness, creative |
| **Maximalist** | Layered elements, rich textures, bold typography | Creative studios, portfolios |

---

## 2. Typography

NiceGUI renders in a browser — load any Google Font via `ui.add_head_html()` inside `setup_theme()`. Body and heading selectors set globally mean component code never needs to specify font families.

### Distinctive Font Pairs

| Aesthetic | Display Font | Body Font |
|-----------|-------------|-----------|
| Luxury/Editorial | Playfair Display | Lato (300, 400) |
| Modern/Minimal | Syne (700, 800) | Syne (400, 500) |
| Industrial | Space Grotesk (700) | IBM Plex Mono (400) |
| Retro-Futuristic | Share Tech Mono | Share Tech Mono |
| Organic/Soft | Cormorant Garamond | Nunito (300, 400, 600) |
| Creative/Bold | Anton | Barlow (400, 500) |
| Dark/Refined | Bebas Neue | Epilogue (300, 400) |
| Art Deco | Poiret One | Josefin Sans (300, 400) |

**Avoid as primary fonts:** Inter, Roboto, Arial, system-ui, Space Grotesk as a default.

### Typography Classes in Component Code
After `setup_theme()` sets the global font, component code uses only Tailwind scale:
```python
# Display heading — font family inherited from setup_theme()'s body selector
ui.label('Dashboard').classes('display text-5xl font-bold tracking-tight')

# Overline
ui.label('METRICS').classes('text-xs font-semibold tracking-widest uppercase text-grey-5')

# Large KPI stat
ui.label('$128,400').classes('text-5xl font-extrabold tabular-nums text-primary')

# Caption
ui.label('Updated 2 min ago').classes('text-xs text-grey-5 italic')
```

### Letter Spacing & Line Height (use `.style()`)
Tailwind doesn't cover extreme values — apply inline:
```python
ui.label('SECTION').style('letter-spacing: 0.25em; line-height: 1')
ui.label('Big Hero').style('font-size: clamp(2.5rem, 6vw, 5rem); line-height: 0.9')
```

---

## 3. Color Strategy

Set the palette inside `setup_theme()` once. Component code then uses only the semantic names `ui.colors()` establishes.

### Choosing a Palette (not generic app-type defaults)

**Monochrome + One Hot Accent** (minimal/brutalist)
```python
ui.colors(primary='#111111', secondary='#444444', accent='#FF4500', positive='#16A34A', negative='#DC2626')
# CSS vars extend beyond ui.colors():
ui.add_css(':root { --bg: #FAFAFA; --surface: #FFFFFF; --border: #111111; }')
```

**Dark Ops** (monitoring/industrial)
```python
ui.colors(primary='#58A6FF', secondary='#21262D', accent='#F78166', positive='#3FB950', negative='#F85149')
ui.add_css(':root { --bg: #080C14; --surface: #0D1117; --border: #21262D; --muted: #8B949E; }')
```

**Warm Editorial** (luxury/content)
```python
ui.colors(primary='#1C1209', secondary='#5C4033', accent='#B5622A', positive='#4A7C59', negative='#C0392B')
ui.add_css(':root { --bg: #F7F2EB; --surface: #FFFDF9; --border: #E8DDD0; }')
```

**Phosphor Terminal** (retro/hacker)
```python
ui.colors(primary='#39FF14', secondary='#1A3A1A', accent='#FFFF00', positive='#39FF14', negative='#FF3131')
ui.add_css(':root { --bg: #0D1117; --surface: #0D1117; --border: #1F3A1F; --muted: #4A7A4A; }')
ui.add_css('body { background: #0D1117; color: #39FF14; }')
```

**Electric on Dark** (modern/SaaS)
```python
ui.colors(primary='#6C63FF', secondary='#3F3D56', accent='#FF6584', positive='#4ADE80', negative='#F87171')
ui.add_css(':root { --bg: #0A0A0F; --surface: #13131A; --border: #1E1E2E; }')
```

### In Component Code — Only Semantic References
```python
# CORRECT: references what setup_theme() defined
ui.button('Save').props('color=primary no-caps')
ui.label('Error').classes('text-negative')
ui.card().style('background: var(--surface); border: 1px solid var(--border)')

# WRONG: raw hex in component code
ui.button('Save').style('background: #58A6FF')  # breaks the contract
```

---

## 4. Motion & Animation

Define all animation keyframes in `setup_theme()`. Component code applies only class names.

### Define in setup_theme()
```python
ui.add_css('''
    @keyframes fadeUp {
        from { opacity: 0; transform: translateY(14px); }
        to   { opacity: 1; transform: translateY(0); }
    }
    @keyframes shimmer {
        from { background-position: -200% 0; }
        to   { background-position:  200% 0; }
    }
    @keyframes pulseDot {
        0%, 100% { opacity: 1; transform: scale(1); }
        50%       { opacity: 0.6; transform: scale(0.85); }
    }

    /* Utility classes applied in component code */
    .anim-in  { animation: fadeUp 0.45s cubic-bezier(0.22,1,0.36,1) both; }
    .delay-1  { animation-delay: 0.06s; }
    .delay-2  { animation-delay: 0.13s; }
    .delay-3  { animation-delay: 0.21s; }
    .delay-4  { animation-delay: 0.30s; }

    .card-hover { transition: transform 0.2s ease, box-shadow 0.2s ease; }
    .card-hover:hover { transform: translateY(-3px); box-shadow: 0 12px 30px rgba(0,0,0,0.2); }

    .skeleton {
        background: linear-gradient(90deg, var(--surface) 25%, var(--border) 50%, var(--surface) 75%);
        background-size: 200% 100%;
        animation: shimmer 1.5s infinite;
    }
    .live-dot {
        display: inline-block; width: 8px; height: 8px; border-radius: 50%;
        background: currentColor;
        animation: pulseDot 2s ease-in-out infinite;
    }
''')
```

### Use in Component Code — Only Class Names
```python
# Staggered page load reveal
header.classes('anim-in')
card1.classes('anim-in delay-1')
card2.classes('anim-in delay-2')
table.classes('anim-in delay-3')

# Hover effect
ui.card().classes('card-hover')

# Skeleton while loading
placeholder = ui.element('div').classes('skeleton').style('height: 48px; border-radius: 8px')

# Live indicator
with ui.row().classes('items-center gap-2'):
    ui.label('').classes('live-dot text-green-500')
    ui.label('Live').classes('text-xs font-semibold text-green-500')
```

### Number Counter (KPI animation via JS bridge)
```python
async def animate_counter(label_el, target: int, duration_ms: int = 800):
    await ui.run_javascript(f'''
        const el = getElement({label_el.id}).$el;
        const target = {target}, duration = {duration_ms};
        const start = performance.now();
        const step = now => {{
            const t = Math.min((now - start) / duration, 1);
            const ease = t < 0.5 ? 2*t*t : -1+(4-2*t)*t;
            el.textContent = Math.round(ease * target).toLocaleString();
            if (t < 1) requestAnimationFrame(step);
        }};
        requestAnimationFrame(step);
    ''')
```

---

## 5. Spatial Composition

Break predictable equal-weight grid layouts. Use NiceGUI's flex/grid + inline styles.

### Asymmetric Hero
```python
with ui.row().classes('w-full items-start gap-8 py-16'):
    with ui.column().classes('gap-4').style('flex: 0 0 58%'):
        ui.label('PLATFORM').classes('text-xs tracking-widest uppercase text-grey-5')
        ui.label('Monitor Everything.').classes('display').style(
            'font-size: clamp(2.5rem,5vw,4.5rem); font-weight: 800; line-height: 0.95; letter-spacing: -0.03em'
        )
        ui.label('Ops dashboard for teams who ship fast.').classes('text-lg text-grey-6 max-w-sm')
    with ui.column().style('flex: 1'):
        kpi_widget()  # floats in the remaining space
```

### Grid-Breaking Decorative Element
```python
with ui.element('div').style('position: relative; overflow: hidden'):
    # Large ghost number — design detail, not interactive
    ui.label('04').style(
        'position: absolute; right: -16px; top: -24px; '
        'font-size: 10rem; font-weight: 900; opacity: 0.04; '
        'line-height: 1; pointer-events: none; user-select: none'
    )
    content()
```

### Off-Center Minimal Layout
```python
# Content pulled left, generous right whitespace
with ui.column().style('padding: 80px 0 80px min(12vw, 100px); max-width: 680px; gap: 2rem'):
    ...
```

### Overlap / Pull-Up
```python
ui.add_css('.pull-up { margin-top: -28px; position: relative; z-index: 1; }')
# Apply to a card that should overlap the element above it
card.classes('pull-up')
```

---

## 6. Backgrounds & Visual Depth

Define in `setup_theme()`'s global CSS. Component code applies class names.

### Gradient Mesh (dark)
```python
ui.add_css('''
    .page-bg {
        background:
            radial-gradient(ellipse at 20% 50%, rgba(108,99,255,0.15) 0%, transparent 55%),
            radial-gradient(ellipse at 80% 20%, rgba(0,180,216,0.10) 0%, transparent 50%),
            var(--bg);
        min-height: 100vh;
    }
''')
ui.query('.nicegui-content').classes('page-bg')
```

### Dot Grid (dark/light)
```python
ui.add_css('''
    .dot-grid {
        background-color: var(--bg);
        background-image: radial-gradient(rgba(255,255,255,0.08) 1px, transparent 1px);
        background-size: 24px 24px;
    }
    .line-grid {
        background-color: var(--bg);
        background-image:
            linear-gradient(var(--border) 1px, transparent 1px),
            linear-gradient(90deg, var(--border) 1px, transparent 1px);
        background-size: 32px 32px;
    }
''')
```

### Grain Overlay (atmosphere)
```python
ui.add_head_html('''
    <style>
        body::after {
            content: '';
            position: fixed; inset: 0; pointer-events: none; z-index: 9999;
            background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.04'/%3E%3C/svg%3E");
            opacity: 0.25;
        }
    </style>
''')
```

### Glassmorphism Card
```python
ui.add_css('''
    .glass {
        background: rgba(255,255,255,0.05);
        backdrop-filter: blur(20px);
        -webkit-backdrop-filter: blur(20px);
        border: 1px solid rgba(255,255,255,0.10);
        border-radius: 16px;
        box-shadow: 0 8px 32px rgba(0,0,0,0.35);
    }
''')
# In component code:
card_el.classes('glass')  # not card_el.style('background: rgba...')
```

### Colored Shadow (accent glow)
```python
# In setup_theme() using the defined accent color:
ui.add_css('''
    .shadow-accent { box-shadow: 0 4px 6px -1px rgba(0,0,0,0.3), 0 20px 40px -8px var(--accent-glow); }
''')
```

### Decorative Dividers
```python
ui.add_css('''
    .divider-glow { height: 1px; background: linear-gradient(90deg, transparent, var(--color-accent) 50%, transparent); margin: 2rem 0; }
    .accent-bar   { height: 3px; width: 40px; background: var(--color-accent); }
''')
```

---

## 7. Anti-Patterns

| Anti-pattern | Fix |
|-------------|-----|
| Raw hex in component code | Move hex to `setup_theme()`, reference semantic name in component |
| `ui.colors(primary='#1565C0')` on every project | Pick a palette that fits this specific app's aesthetic |
| Inter/Roboto/Arial as only font | Load a distinctive Google Font pair in `setup_theme()` |
| Flat white/grey card on white background | Add dot grid, gradient mesh, or tinted surface via `setup_theme()` |
| All elements same visual weight | Create hierarchy — one dominant element per view |
| Scattered `style()` calls with the same values | Define CSS class in `setup_theme()`, apply class name in components |
| Defining animation keyframes inside a component | Define in `setup_theme()`, apply class name in component |
| No empty states or loading states | Always design for empty + skeleton loading |

---

## 8. Complete setup_theme() Recipes

Copy, customize palette, then call once at app startup.

### Recipe A — Dark Ops / Monitoring
```python
def setup_theme():
    ui.add_head_html('''
        <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Syne:wght@600;800&display=swap" rel="stylesheet">
        <style>
            body, .q-app { font-family: 'JetBrains Mono', monospace; background: #080C14; color: #C9D1D9; }
            .display { font-family: 'Syne', sans-serif; }
        </style>
    ''')
    ui.colors(
        primary='#58A6FF', secondary='#21262D', accent='#F78166',
        positive='#3FB950', negative='#F85149', info='#58A6FF', warning='#D29922',
    )
    ui.add_css('''
        :root { --bg:#080C14; --surface:#0D1117; --border:#21262D; --muted:#8B949E; --accent-glow:rgba(88,166,255,0.18); }
        .nicegui-content { background: var(--bg); min-height: 100vh; }
        .surface { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; }
        @keyframes fadeUp { from{opacity:0;transform:translateY(12px)} to{opacity:1;transform:translateY(0)} }
        .anim-in  { animation: fadeUp 0.45s cubic-bezier(0.22,1,0.36,1) both; }
        .delay-1  { animation-delay: 0.06s; } .delay-2 { animation-delay: 0.14s; }
        .delay-3  { animation-delay: 0.23s; } .delay-4 { animation-delay: 0.33s; }
        .card-hover { transition: transform .2s ease, box-shadow .2s ease; }
        .card-hover:hover { transform: translateY(-2px); box-shadow: 0 12px 30px rgba(0,0,0,0.4); }
        .shadow-accent { box-shadow: 0 4px 6px rgba(0,0,0,.3), 0 16px 32px var(--accent-glow); }
        .dot-grid { background-color: var(--bg); background-image: radial-gradient(rgba(255,255,255,0.06) 1px, transparent 1px); background-size: 24px 24px; }
    ''')
```

**Component code with this theme:**
```python
# Only semantic references — no hex, no font names
with ui.card().classes('surface card-hover shadow-accent anim-in delay-1'):
    ui.label('LATENCY').classes('text-xs tracking-widest uppercase').style('color: var(--muted)')
    ui.label('12ms').classes('display text-5xl font-bold text-primary')
    ui.label('p99 over last 5min').classes('text-xs').style('color: var(--muted)')
```

---

### Recipe B — Warm Editorial / Luxury Light
```python
def setup_theme():
    ui.add_head_html('''
        <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,600;0,700;1,400&family=Lato:wght@300;400;700&display=swap" rel="stylesheet">
        <style>
            body, .q-app { font-family: 'Lato', sans-serif; background: #F7F2EB; color: #1C1209; }
            .display { font-family: 'Playfair Display', serif; }
            .overline { font-family: 'Lato'; font-size: 0.7rem; letter-spacing: 0.15em; text-transform: uppercase; font-weight: 700; }
        </style>
    ''')
    ui.colors(
        primary='#1C1209', secondary='#5C4033', accent='#B5622A',
        positive='#4A7C59', negative='#C0392B', warning='#E67E22',
    )
    ui.add_css('''
        :root { --bg:#F7F2EB; --surface:#FFFDF9; --border:#E8DDD0; --gold:#C8962A; }
        .nicegui-content { background: var(--bg); }
        .card-editorial { background: var(--surface); border: 1px solid var(--border); border-radius: 4px; box-shadow: 0 2px 20px rgba(28,18,9,0.07); }
        @keyframes fadeUp { from{opacity:0;transform:translateY(10px)} to{opacity:1} }
        .anim-in { animation: fadeUp 0.5s cubic-bezier(0.22,1,0.36,1) both; }
        .delay-1 { animation-delay:0.07s; } .delay-2 { animation-delay:0.16s; }
        .accent-bar { height:2px; width:36px; background: var(--gold); }
    ''')
```

---

### Recipe C — Brutalist Minimal (Tools / CLIs)
```python
def setup_theme():
    ui.add_head_html('''
        <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600;700&display=swap" rel="stylesheet">
        <style>
            body, .q-app, * { font-family: 'IBM Plex Mono', monospace !important; background: #FAFAFA; color: #111; }
        </style>
    ''')
    ui.colors(
        primary='#111111', secondary='#333333', accent='#FF4500',
        positive='#008000', negative='#FF0000', warning='#FF8C00',
    )
    ui.add_css('''
        :root { --bg:#FAFAFA; --surface:#FFFFFF; --border:#111111; --accent:#FF4500; }
        * { border-radius: 0 !important; }
        .nicegui-content { background: var(--bg); }
        .card-brutal { border: 2px solid var(--border); box-shadow: 4px 4px 0 var(--border); background: var(--surface); }
        .card-brutal:hover { box-shadow: 6px 6px 0 var(--border); transform: translate(-2px,-2px); transition: all 0.1s; }
        .accent-bar { width:100%; height:3px; background: var(--accent); }
        @keyframes fadeIn { from{opacity:0} to{opacity:1} }
        .anim-in { animation: fadeIn 0.3s ease both; }
    ''')
```
