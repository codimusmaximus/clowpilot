# clowpilot

## Running

Docker is the canonical setup:

```bash
docker compose up --build
```

This starts:

- frontend on `http://localhost:3000`
- backend on `http://localhost:8000`
- the shared workspace mounted at `/workspace` inside the backend container

For local backend development, run the API with the project workspace explicitly configured so file and image paths resolve consistently:

```bash
cd backend
WORKSPACE_DIR=../workspace uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

For local frontend development:

```bash
cd frontend
pnpm install
pnpm dev
```

Image rendering in chat and the workspace pane is served through `/api/workspace/image`. The backend now accepts both workspace-relative paths and absolute `file://` or host filesystem paths that point inside this repo's `workspace/` directory.
