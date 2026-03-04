# AgentSkills

A central repo for Claude Code skills and their reference dependency projects.

## Structure

```
AgentSkills/
├── skills/                  # Claude Code skill definitions
│   ├── fastapi-skill/       # FastAPI skill (SKILL.md, assets, agents, references)
│   └── nicegui-skill/       # NiceGUI skill (SKILL.md, examples, references)
├── fastapi/                 # FastAPI reference project & dependency exploration
└── nicegui/                 # NiceGUI reference project & dependency exploration
```

## Skills

| Skill | Description |
|-------|-------------|
| `fastapi-skill` | FastAPI REST API development, testing, deployment, Pydantic, JWT/OAuth2 |
| `nicegui-skill` | NiceGUI Python UI — components, layouts, async, data binding, auth |

## Usage

Skills are registered via `.claude-plugin/plugin.json` and loaded by Claude Code.
Each skill's `SKILL.md` is the main instruction file consumed at runtime.
