# Copilot UI Experiment — Plan

A working example of an [assistant-ui](https://www.assistant-ui.com/) copilot
with a FastAPI backend, three-pane workspace layout, and inline tool-call UI
that projects artefacts onto a right-hand workspace.

## Concept

A copilot that *narrates in chat* and *shows in the workspace*. The chat is
where the assistant explains what it's doing (with tool-call status rendered
inline using assistant-ui primitives). The right pane is where it actually
puts things: opened files, highlighted regions with pinned comments, ad-hoc
markdown/HTML snippets.

## Layout

```
┌──────────────┬──────────────────────┬───────────────────────────┐
│  Sidebar     │  Chat (centre)       │  Workspace (right)        │
│              │                      │                           │
│  Threads     │  Messages            │  Tab bar                  │
│  ──────      │   • user             │  ─ welcome.md  ─ snippet  │
│              │   • assistant text   │                           │
│  File tree   │   • tool-call card   │  Active tab content:      │
│   notes/     │     (inline status,  │   • file viewer with      │
│   ▸ welcome  │      args, summary)  │     line numbers + gutter │
│   data/      │   • assistant text   │     highlights + pinned   │
│   ▸ csv      │                      │     comments              │
│              │  Composer            │   • markdown / html       │
│              │                      │     snippet renderer      │
└──────────────┴──────────────────────┴───────────────────────────┘
```

## Stack

| Layer       | Choice                                                      |
|-------------|-------------------------------------------------------------|
| Frontend    | Next.js 15 (App Router) + TypeScript + Tailwind v4          |
| Chat UI     | `@assistant-ui/react` primitives + `useExternalStoreRuntime`|
| Markdown    | `react-markdown` + `remark-gfm` + `rehype-highlight`        |
| State       | `zustand` — shared store between chat tools and workspace   |
| Backend     | FastAPI + Anthropic Python SDK (streaming, tool use)        |
| Transport   | SSE (`text/event-stream`) with custom JSON-event protocol   |
| Sandbox     | `backend/workspace/` — all file ops sandboxed under here    |

## Tools (server-side)

All six tools execute on the backend inside the sandbox. Each one returns a
JSON payload that the frontend renders in two places: a compact card inline
in chat, and (for the workspace tools) a tab/overlay in the right pane.

| Tool           | Purpose                                                |
|----------------|--------------------------------------------------------|
| `list_tree`    | Walk the workspace and return a nested tree            |
| `read_file`    | Return file contents (no side-effect on UI)            |
| `write_file`   | Create / overwrite a file (`path`, `content`, `type?`) |
| `display_file` | Open a file as a tab in the right-hand workspace       |
| `highlight`    | Highlight a line range in the open file + pin comment  |
| `snippet`      | Render an ad-hoc markdown / HTML tab                   |

## Event protocol (SSE)

Each event is a single JSON line under `data:`:

```jsonc
{"type": "text-delta",            "delta": "..."}
{"type": "tool-call-start",       "id": "...", "name": "..."}
{"type": "tool-call-input-delta", "id": "...", "delta": "{\"pa"}
{"type": "tool-call-input",       "id": "...", "name": "...", "input": { ... }}
{"type": "tool-result",           "id": "...", "name": "...", "result": { ... }}
{"type": "error",                 "message": "..."}
{"type": "done"}
```

The frontend folds these into assistant-ui ThreadMessage parts:
- `text-delta` → appends to the current `text` part
- `tool-call-*` → builds up a `tool-call` part (status: streaming → input
  → executing → result)

## Aesthetic — "Editorial Lab"

A single, committed direction. Not a generic AI demo skin.

- **Ground**: warm off-black (`#0e0d0a`) with a faint grain overlay
- **Foreground**: bone (`#ece7dc`)
- **Accent**: ember (`#d96833`) — used sparingly: focus rings, active tab,
  tool-call running indicators, highlight gutters
- **Borders**: hairline `rgba(236,231,220,0.08)` — research-notebook feel
- **Typography**:
  - Display: **Instrument Serif** italic — used for headings, tab titles,
    the app mark
  - Body: **Geist** (technical grotesque)
  - Mono: **JetBrains Mono** — file viewer, code blocks, tool args
- **Detail**: small caps section labels, lining figures, tabular numerals
  in the file viewer gutter, a faint horizontal rule under the chat header

## Demo flow

1. App loads. Sidebar shows seeded `notes/welcome.md` and `data/customers.csv`.
   Right pane shows an empty-state with hint text.
2. User: *"Read the welcome note and walk me through it."*
3. Assistant calls `display_file(notes/welcome.md)` → tab opens on the right.
4. Assistant calls `highlight(...)` two or three times → ember gutters appear
   alongside the corresponding line ranges, each with a pinned comment.
5. Assistant emits a brief text response in chat — the workspace carries the
   teaching.
6. User: *"Make me a one-pager TL;DR"* → assistant calls `snippet(format=markdown, content=...)`
   → snippet tab opens.
7. User: *"Save that as `notes/tldr.md`"* → assistant calls `write_file(...)`
   → file appears in sidebar tree.

## Build order

1. ✅ Scaffold Next.js + FastAPI, install deps.
2. ✅ Backend tools + agent loop + chat / file routes.
3. ⏳ Frontend zustand store (workspace tabs, highlights, file tree).
4. ⏳ Three-pane layout shell with the editorial-lab aesthetic.
5. ⏳ Chat: assistant-ui primitives + per-tool inline UI components.
6. ⏳ Workspace pane: tab bar + file viewer w/ highlights + snippet renderer.
7. ⏳ Sidebar: tree view + (placeholder) thread list.
8. ⏳ End-to-end run; polish typography, spacing, transitions.

## Run

```bash
# backend
cd backend && cp .env.example .env  # fill in ANTHROPIC_API_KEY
uv run uvicorn main:app --reload

# frontend
cd frontend && pnpm dev
```

Then open http://localhost:3000.
