# TODO

## 1. Move chats into folders (use projects — no new concept)

Decision: **projects ARE the folders.** Don't add a separate folder table. A
project already groups chats (`conversations.project_id`) and its "knowledge"
(pinned pages) is optional — a project with nothing pinned is just a plain
folder. Most of this already exists; close the gaps.

Already done:
- Sidebar groups chats into "ungrouped" + per-project buckets.
- Create / delete project, new-chat-in-project (`sidebar.tsx`, `chat-store.ts`).
- Backend move API exists: `PUT /api/conversations/{id}/project` (`set_conversation_project`).

To build:
- **Move an existing chat into a folder/project** — the missing piece. Add a
  per-chat "move to…" menu (or drag-drop) in the sidebar that calls the existing
  `PUT /api/conversations/{id}/project` endpoint; add a `moveConversation(id, projectId|null)`
  action to `chat-store.ts` and refresh the list. Include "Remove from folder"
  (projectId = null → back to ungrouped).
- **Rename project** — add `PUT /api/projects/{id}` + inline rename in the sidebar
  (only create/delete exist today).
- **Optional polish:** rename the "project" label to "folder" in the UI if we want
  folder-first language; de-emphasize the knowledge UI so an empty project reads as
  a plain folder. Knowledge stays available for power use, just not front-and-center.

## 2. Python code execution via a Docker sandbox (persistent volume)

Give the agent a tool to run Python in an isolated Docker container, with work
persisted on a mounted volume.

- **Build on the existing `plugins/container.py`** — it already manages a persistent
  Docker container (`copilot-workspace-container`) bind-mounting the app workspace and
  exposes `run_command` / file read/write. Extend rather than duplicate.
- **Add a focused `run_python(code, ...)` tool:** write the snippet to the mounted
  workspace and execute it in the container (`python -`), returning stdout/stderr +
  exit code. Capture and surface tracebacks.
- **Persistence:** confirm the volume mount survives container restarts (a named Docker
  volume or the bind-mounted `workspace/`), so installed packages / generated files stick.
  Decide: persist pip installs (named volume for site-packages) vs. ephemeral per-run.
- **Safety / limits:** resource caps (CPU/mem via `docker run` flags), execution timeout,
  no host network unless needed. It's a single-user personal app, but still sandbox.
- **UX:** stream output back as it runs; show generated files/plots in the workspace pane
  (the image/snippet flow already exists in the system prompt).

## 3. Image display is broken (workspace-directory mismatch)

Symptom: images don't render in chat or the workspace pane.

What works (verified): the wiring is fine end-to-end —
- Chat: `markdown.tsx` `WorkspaceImage` → `normalizeWorkspaceImagePath` →
  `workspaceImageUrl` (relative `/api/workspace/image?path=…`, proxied to the
  backend by the `next.config.ts` rewrite).
- Workspace pane: `display_image` tool → chat-store `case "display_image"` →
  `ws.openImage(path, url)` → `ImageViewer` renders `tab.url`.
- Backend `/api/workspace/image` returns `200 image/png` for files that exist in
  the backend's `WORKSPACE` (tested directly and through the `:3000` proxy).

Root cause: **there are two `workspace/` dirs and `WORKSPACE` is CWD-dependent.**
`tools.py`: `WORKSPACE = Path(os.environ.get("WORKSPACE_DIR", "./workspace")).resolve()`.
- Run locally from `backend/` → `WORKSPACE = backend/workspace/`.
- Docker (`docker-compose.yml`) → `WORKSPACE_DIR=/workspace`, mounting repo-root `./workspace`.
So `report/transactions_plot.png` (lives in repo-root `workspace/`) → **404**, while
`plot.png` (in `backend/workspace/`) → **200**. Whichever dir the backend wasn't
launched against serves broken images.

Fix options (pick one):
- Pin `WORKSPACE_DIR` to a single canonical dir for local dev too (e.g. set it in
  `backend/.env`), and consolidate the two `workspace/` folders into one.
- Or make `WORKSPACE` resolve to a fixed location independent of CWD (e.g. relative
  to the repo root / a configured data dir), not `./workspace`.
- Then re-test: a generated plot referenced as `![](report/foo.png)` in chat AND
  via `display_image` should both render.

Secondary check while here: confirm images created via the pages/files plugins land
on disk under `WORKSPACE` (the image endpoint reads disk via `_safe_path`, not the
DB) — DB-only entries would also 404.

**Status (fix applied):** pinned `WORKSPACE_DIR` (→ repo-root `workspace/`, the dir
with the real data + what Docker mounts) and `SQLITE_DB_PATH` (→ the active
`backend/copilot.sqlite3`) as absolute paths in `backend/.env`, so resolution no
longer depends on the launch directory. `report/transactions_plot.png` now serves.
Remaining: (a) the two `workspace/` dirs + two `copilot.sqlite3` files should be
consolidated to avoid future split-brain; (b) `outputs/*.png` referenced by old
messages are unrecoverable — they were generated in an ephemeral container (see #2);
(c) check markdown image refs with spaces/non-ASCII in the path (accounting folders)
render — markdown may need `<...>`-wrapped URLs.

## 4. Streaming "thinking" (reasoning) output

Stream the model's reasoning/thinking, not just the final answer + tool calls.

- **Backend (`agent.py`):** pydantic-ai surfaces thinking via `ThinkingPart` /
  `ThinkingPartDelta` events in `run_stream_events` — currently only `TextPart`,
  `ToolCallPart`, and tool events are handled in `_stream_model`. Add handling that
  emits a new SSE event type (e.g. `{"type":"thinking-delta","delta":...}`).
  - Requires enabling thinking on the model (provider-specific: e.g. Anthropic
    extended thinking / OpenAI reasoning). Gate per-provider; not all support it.
- **Frontend (`chat.tsx`, `chat-store.ts`, message types):** render thinking in a
  collapsible "thinking" block above the answer, streamed live, visually distinct
  from the final text. Persist or drop per preference (probably drop from saved
  history to save tokens, or store collapsed).

## 5. Tool-call rendering & streaming — render by type

Today tool calls render generically. Make rendering type-aware and fix streaming.

- **Current flow:** `agent.py` emits `tool-call-start` / `tool-call-input-delta`
  (streamed args) / `tool-call-input` / `tool-result`; the frontend shows a generic
  tool chip. Audit that the streamed arg deltas actually render incrementally and
  that results display cleanly (some results are large dicts / JSON).
- **Render per tool type** — a registry mapping tool name → renderer, e.g.:
  - `display_image` → thumbnail/preview
  - `snippet` → rendered markdown/html preview (already opens a workspace tab)
  - `highlight` → file + line range chip
  - `web_search` / `scrape_url` → result list with links
  - `outlook_*` → mail/event summary cards
  - default → collapsible JSON args + result
- **Streaming:** show args building up live, then a spinner until `tool-result`,
  then the typed result view. Handle interrupted/failed calls (the
  `"Tool call failed…"` shape) distinctly.
- Files: `chat.tsx` (tool chip rendering), `chat-store.ts` (event handling),
  `lib/types.ts` (`ToolCallStatus`).
