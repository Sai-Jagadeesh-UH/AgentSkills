# NiceGUI UI Plugin

A Claude Code plugin providing deep expertise in building Python UIs with [NiceGUI](https://nicegui.io).

## What This Plugin Does

Gives Claude comprehensive knowledge of NiceGUI patterns, components, and best practices distilled from 50+ real-world example apps so it can build production-quality NiceGUI UIs immediately.

## Skills

### `nicegui-skill`

Triggered when you ask Claude to build NiceGUI apps, components, pages, or anything UI-related with NiceGUI/Python.

**Covers:**
- All core UI components (inputs, tables, dialogs, media, 3D)
- Layout & Tailwind CSS styling
- Async patterns and event handling
- Data binding and `@ui.refreshable`
- Authentication (middleware, OAuth2, session storage)
- FastAPI integration, databases, websockets
- Custom Vue/JS components and element subclassing
- Multi-page routing and modular architecture
- Testing with `Screen` and `User` fixtures

## Structure

```
.
├── .claude-plugin/
│   └── plugin.json
├── README.md
├── skills/
│   └── nicegui-skill/
│       ├── SKILL.md               # Core skill - always loaded when triggered
│       ├── references/
│       │   ├── components.md      # All UI components with examples
│       │   ├── layouts-and-styling.md
│       │   ├── async-and-events.md
│       │   ├── data-binding.md
│       │   ├── auth-and-storage.md
│       │   ├── integrations.md    # FastAPI, DB, WS, Redis, Stripe
│       │   ├── custom-components.md
│       │   ├── architecture.md
│       │   └── testing.md
│       └── examples/
│           ├── basic_app.py
│           ├── auth_app.py
│           ├── crud_table.py
│           └── chat_app.py
└── examples/                      # Source examples (reference material)
```

## Installation

Install this plugin locally with Claude Code:

```bash
cc --plugin-dir /path/to/ClaudeSkills
```

Or add to your Claude Code settings:

```json
{
  "pluginDirectories": ["/path/to/ClaudeSkills"]
}
```
