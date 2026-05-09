"""FastAPI app for the assistant-ui copilot example.

- POST /api/chat   : stream agent events for a conversation
- GET  /api/tree   : current workspace file tree (sidebar)
- GET  /api/file   : read a file from the workspace
- POST /api/upload : upload a file into the workspace
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import tools
import db
from agent import (
    BASE_SYSTEM_PROMPT,
    get_active_model,
    list_available_models,
    run,
    set_active_model,
    split_messages,
)
from plugins import registry as plugin_registry

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


class AppMessage(BaseModel):
    id: str
    role: str
    parts: list[dict[str, Any]]
    createdAt: int
    parentId: str | None = None


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    conversationId: str | None = None
    systemPromptId: str | None = None


class MessagesRequest(BaseModel):
    messages: list[AppMessage]
    headId: str | None = None


class ConversationRequest(BaseModel):
    title: str | None = None
    systemPromptId: str | None = None
    projectId: str | None = None


class ProjectRequest(BaseModel):
    name: str
    systemPromptId: str | None = None


class ConversationProjectRequest(BaseModel):
    projectId: str | None = None


class SystemPromptRequest(BaseModel):
    name: str
    content: str


class ActiveSystemPromptRequest(BaseModel):
    id: str


class ActiveModelRequest(BaseModel):
    model: str


class PluginSettingsRequest(BaseModel):
    enabled: bool
    config: dict[str, Any] | None = None


@app.post("/api/chat")
async def chat(req: ChatRequest):
    raw = [m.model_dump() for m in req.messages]
    prompt, history = split_messages(raw)
    conversation = db.ensure_conversation(req.conversationId)
    conversation_id = conversation["id"]
    system_prompt_id = req.systemPromptId or conversation.get("systemPromptId")
    system_prompt_row = db.get_system_prompt(system_prompt_id) if system_prompt_id else None
    
    # We pass None for base_prompt to use the default BASE_SYSTEM_PROMPT
    # inside agent._compose_system_prompt
    base_prompt = system_prompt_row["content"] if system_prompt_row else None

    async def gen():
        try:
            async for event in run(prompt, history, conversation_id, base_prompt):
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


@app.get("/api/conversations")
def get_conversations():
    conversation = db.ensure_conversation()
    conversations = db.list_conversations()
    return {"conversations": conversations, "activeConversationId": conversation["id"]}


@app.post("/api/conversations")
def post_conversation(req: ConversationRequest):
    prompt_id = req.systemPromptId or db.get_active_system_prompt_id()
    if prompt_id and db.get_system_prompt(prompt_id) is None:
        raise HTTPException(404, f"system prompt not found: {prompt_id}")
    if req.projectId and db.get_project(req.projectId) is None:
        raise HTTPException(404, f"project not found: {req.projectId}")
    return db.create_conversation(req.title or "New chat", prompt_id, req.projectId)


@app.delete("/api/conversations/{conversation_id}")
def delete_conversation_endpoint(conversation_id: str):
    if not db.conversation_exists(conversation_id):
        raise HTTPException(404, f"conversation not found: {conversation_id}")
    db.delete_conversation(conversation_id)
    return {"ok": True}


@app.put("/api/conversations/{conversation_id}/project")
def put_conversation_project(conversation_id: str, req: ConversationProjectRequest):
    conversation = db.set_conversation_project(conversation_id, req.projectId)
    if conversation is None:
        raise HTTPException(404, f"conversation not found: {conversation_id}")
    return conversation


@app.put("/api/conversations/{conversation_id}/system-prompt")
def put_conversation_system_prompt(conversation_id: str, req: ActiveSystemPromptRequest):
    if db.get_system_prompt(req.id) is None:
        raise HTTPException(404, f"system prompt not found: {req.id}")
    conversation = db.set_conversation_system_prompt(conversation_id, req.id)
    if conversation is None:
        raise HTTPException(404, f"conversation not found: {conversation_id}")
    return conversation


@app.get("/api/conversations/{conversation_id}/messages")
def get_messages(conversation_id: str):
    if not db.conversation_exists(conversation_id):
        raise HTTPException(404, f"conversation not found: {conversation_id}")
    return {
        "messages": db.get_messages(conversation_id),
        "headId": db.get_head_message_id(conversation_id),
    }


@app.put("/api/conversations/{conversation_id}/messages")
def put_messages(conversation_id: str, req: MessagesRequest):
    if not db.conversation_exists(conversation_id):
        raise HTTPException(404, f"conversation not found: {conversation_id}")
    db.replace_messages(conversation_id, [m.model_dump() for m in req.messages], req.headId)
    return {"ok": True}


@app.get("/api/system-prompts")
def get_system_prompts():
    prompt = db.ensure_system_prompt("Workspace copilot", BASE_SYSTEM_PROMPT)
    return {
        "prompts": db.list_system_prompts(),
        "activeSystemPromptId": db.get_active_system_prompt_id() or prompt["id"],
    }


@app.post("/api/system-prompts")
def post_system_prompt(req: SystemPromptRequest):
    prompt = db.create_system_prompt(req.name, req.content)
    db.set_active_system_prompt(prompt["id"])
    return prompt


@app.put("/api/system-prompts/active")
def put_active_system_prompt(req: ActiveSystemPromptRequest):
    if db.get_system_prompt(req.id) is None:
        raise HTTPException(404, f"system prompt not found: {req.id}")
    db.set_active_system_prompt(req.id)
    return {"ok": True, "activeSystemPromptId": req.id}


@app.put("/api/system-prompts/{prompt_id}")
def put_system_prompt(prompt_id: str, req: SystemPromptRequest):
    prompt = db.update_system_prompt(prompt_id, req.name, req.content)
    if prompt is None:
        raise HTTPException(404, f"system prompt not found: {prompt_id}")
    return prompt


# ---------- models ----------


@app.get("/api/models")
def get_models():
    return {
        "models": list_available_models(),
        "activeModel": get_active_model(),
    }


@app.put("/api/models/active")
def put_active_model(req: ActiveModelRequest):
    available = {m["model"] for m in list_available_models()}
    if req.model not in available:
        raise HTTPException(400, f"model not available: {req.model}")
    set_active_model(req.model)
    return {"ok": True, "activeModel": req.model}


# ---------- projects ----------


@app.get("/api/projects")
def get_projects():
    return {"projects": db.list_projects()}


@app.post("/api/projects")
def post_project(req: ProjectRequest):
    if req.systemPromptId and db.get_system_prompt(req.systemPromptId) is None:
        raise HTTPException(404, f"system prompt not found: {req.systemPromptId}")
    return db.create_project(req.name, req.systemPromptId)


@app.delete("/api/projects/{project_id}")
def delete_project_endpoint(project_id: str):
    if db.get_project(project_id) is None:
        raise HTTPException(404, f"project not found: {project_id}")
    db.delete_project(project_id)
    return {"ok": True}


# ---------- plugins ----------


@app.get("/api/plugins")
def get_plugins():
    return {"plugins": plugin_registry.list_plugin_status()}


@app.put("/api/plugins/{plugin_id}")
def put_plugin(plugin_id: str, req: PluginSettingsRequest):
    plugin_ids = {plugin.id for plugin in plugin_registry.load_plugins()}
    if plugin_id not in plugin_ids:
        raise HTTPException(404, f"plugin not found: {plugin_id}")
    return db.set_plugin_enabled(plugin_id, req.enabled, req.config)


@app.get("/api/conversations/{conversation_id}/plugins")
def get_conversation_plugins(conversation_id: str):
    if not db.conversation_exists(conversation_id):
        raise HTTPException(404, f"conversation not found: {conversation_id}")
    return {"plugins": plugin_registry.list_plugin_status(conversation_id)}


@app.put("/api/conversations/{conversation_id}/plugins/{plugin_id}")
def put_conversation_plugin(
    conversation_id: str, plugin_id: str, req: PluginSettingsRequest
):
    if not db.conversation_exists(conversation_id):
        raise HTTPException(404, f"conversation not found: {conversation_id}")
    plugin_ids = {plugin.id for plugin in plugin_registry.load_plugins()}
    if plugin_id not in plugin_ids:
        raise HTTPException(404, f"plugin not found: {plugin_id}")
    db.set_conversation_plugin_enabled(
        conversation_id, plugin_id, req.enabled, req.config
    )
    return {"ok": True}


class ToolToggleRequest(BaseModel):
    enabled: bool


@app.put("/api/conversations/{conversation_id}/plugins/{plugin_id}/tools/{tool_name}")
def put_conversation_tool(
    conversation_id: str, plugin_id: str, tool_name: str, req: ToolToggleRequest
):
    if not db.conversation_exists(conversation_id):
        raise HTTPException(404, f"conversation not found: {conversation_id}")
    db.set_conversation_tool_enabled(conversation_id, plugin_id, tool_name, req.enabled)
    return {"ok": True}


# ---------- workspace ----------


@app.get("/api/tree")
def get_tree(path: str = ""):
    return tools.list_tree(path)


@app.get("/api/pages/tree")
def get_pages_tree(path: str = ""):
    return tools.page_list_tree(path)


@app.get("/api/files/tree")
def get_files_tree():
    return tools.disk_list_tree()


@app.get("/api/file")
def get_file(path: str):
    res = tools.read_file(path)
    if "error" in res:
        raise HTTPException(404, res["error"])
    return res


@app.post("/api/upload")
async def upload(file: UploadFile, folder: str = ""):
    tools._safe_path(folder) if folder else tools.WORKSPACE
    name = Path(file.filename or "upload.bin").name
    rel = f"{folder.strip('/')}/{name}".strip("/")
    content = (await file.read()).decode("utf-8", errors="replace")
    return db.upsert_file(rel, content, tools._ext_kind(Path(name)))


@app.get("/api/search")
def get_search(q: str, limit: int = 5, kind: str | None = None):
    return db.search_chunks(q, limit=min(limit, 20), kind_filter=kind)


@app.delete("/api/file")
def delete_file(path: str):
    rel = str(tools._safe_path(path).relative_to(tools.WORKSPACE))
    result = tools.delete_file(rel)
    if "error" in result:
        raise HTTPException(404, f"not found: {path}")
    return result


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
        if db.file_exists(rel):
            continue
        db.upsert_file(rel, content, tools._ext_kind(Path(rel)))


SYSTEM_PROMPT_PRESETS = [
    (
        "Workspace copilot",
        BASE_SYSTEM_PROMPT,
    ),
    (
        "Concise operator",
        BASE_SYSTEM_PROMPT
        + "\n\nStyle override:\n"
        + "- Be terse and action-oriented.\n"
        + "- Prefer tool use over explanation when the user asks for changes.\n"
        + "- Summarize outcomes in one or two sentences unless detail is requested.\n",
    ),
    (
        "Careful reviewer",
        BASE_SYSTEM_PROMPT
        + "\n\nReview mode:\n"
        + "- Prioritize correctness, edge cases, regressions, and missing tests.\n"
        + "- When reviewing, list findings first with file or line references when available.\n"
        + "- Avoid broad rewrites unless they directly reduce risk.\n",
    ),
    (
        "Teaching copilot",
        BASE_SYSTEM_PROMPT
        + "\n\nTeaching mode:\n"
        + "- Explain decisions briefly as you work.\n"
        + "- Use highlights and rendered snippets to make concepts visible.\n"
        + "- Keep examples concrete and tied to files in the workspace.\n",
    ),
]


def _seed_system_prompts():
    for name, content in SYSTEM_PROMPT_PRESETS:
        if db.get_system_prompt_by_name(name):
            continue
        prompt = db.create_system_prompt(name, content)
        if name == "Workspace copilot" and db.get_active_system_prompt_id() is None:
            db.set_active_system_prompt(prompt["id"])


def _seed_plugins():
    db.set_plugin_enabled("core.pages", True)
    db.set_plugin_enabled("core.files", True)
    db.set_plugin_enabled("core.workspace", True)
    db.set_plugin_enabled("core.websearch", True)


_seed()
_seed_system_prompts()
_seed_plugins()
db.ensure_system_prompt("Workspace copilot", BASE_SYSTEM_PROMPT)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
