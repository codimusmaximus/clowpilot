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
