"""FastAPI app for the assistant-ui copilot example.

- POST /api/chat   : stream agent events for a conversation
- GET  /api/tree   : current workspace file tree (sidebar)
- GET  /api/file   : read a file from the workspace
- POST /api/upload : upload a file into the workspace
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import tools
from agent import run, split_messages

load_dotenv()

app = FastAPI(title="copilot-ui-exp backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- chat ----------


class ChatPart(BaseModel):
    type: str
    text: str | None = None
    id: str | None = None
    name: str | None = None
    input: dict[str, Any] | None = None
    result: Any = None


class ChatMessage(BaseModel):
    role: str
    content: str | list[ChatPart]


class ChatRequest(BaseModel):
    messages: list[ChatMessage]


@app.post("/api/chat")
async def chat(req: ChatRequest):
    raw = [m.model_dump() for m in req.messages]
    prompt, history = split_messages(raw)

    async def gen():
        try:
            async for event in run(prompt, history):
                yield f"data: {json.dumps(event, default=str)}\n\n"
        except Exception as e:  # noqa: BLE001
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ---------- workspace ----------


@app.get("/api/tree")
def get_tree(path: str = ""):
    return tools.list_tree(path)


@app.get("/api/file")
def get_file(path: str):
    res = tools.read_file(path)
    if "error" in res:
        raise HTTPException(404, res["error"])
    return res


@app.post("/api/upload")
async def upload(file: UploadFile, folder: str = ""):
    folder_path = tools._safe_path(folder) if folder else tools.WORKSPACE
    folder_path.mkdir(parents=True, exist_ok=True)
    name = Path(file.filename or "upload.bin").name
    dest = folder_path / name
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    return {
        "path": str(dest.relative_to(tools.WORKSPACE)),
        "bytes": dest.stat().st_size,
        "kind": tools._ext_kind(dest),
    }


@app.delete("/api/file")
def delete_file(path: str):
    p = tools._safe_path(path)
    if not p.exists():
        raise HTTPException(404, f"not found: {path}")
    if p.is_dir():
        shutil.rmtree(p)
    else:
        p.unlink()
    return {"ok": True}


def _seed():
    samples = {
        "notes/welcome.md": (
            "# Welcome to the workspace\n\n"
            "This sandbox is your scratch surface. Ask the assistant to:\n\n"
            "- list, read, or create files\n"
            "- display a file in the right pane\n"
            "- highlight a region with a pinned comment\n"
            "- render an ad-hoc markdown or HTML snippet\n\n"
            "Try: *Create a Python script that parses CSV and walk me through it.*\n"
        ),
        "data/customers.csv": (
            "id,name,plan,mrr\n"
            "1,Acme Inc,Enterprise,4800\n"
            "2,Globex,Pro,890\n"
            "3,Initech,Pro,890\n"
            "4,Umbrella,Enterprise,9200\n"
            "5,Hooli,Starter,49\n"
        ),
    }
    for rel, content in samples.items():
        p = tools.WORKSPACE / rel
        if p.exists():
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")


_seed()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
