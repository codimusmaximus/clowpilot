"""FastAPI app for the assistant-ui copilot example.

- POST /api/chat   : stream agent events for a conversation
- GET  /api/tree   : current workspace file tree (sidebar)
- GET  /api/file   : read a file from the workspace
- POST /api/upload : upload a file into the workspace
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
import mimetypes

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

import tools
import db
from agent import (
    BASE_SYSTEM_PROMPT,
    compose_system_prompt,
    get_active_model,
    list_available_models,
    run,
    set_active_model,
    split_messages,
)
from plugins import registry as plugin_registry
from plugins import mcp_servers
from plugins import outlook as outlook_plugin

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
    attachments: list[dict[str, Any]] | None = None


class AppMessage(BaseModel):
    id: str
    role: str
    parts: list[dict[str, Any]]
    createdAt: int
    parentId: str | None = None
    attachments: list[dict[str, Any]] | None = None


class AttachmentUploadResponse(BaseModel):
    id: str
    path: str
    name: str
    contentType: str
    kind: str
    bytes: int
    createdAt: int
    updatedAt: int


class AttachmentListResponse(BaseModel):
    attachments: list[AttachmentUploadResponse]


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


class ProjectKnowledgeRequest(BaseModel):
    refType: str
    refPath: str


class ProjectKnowledgeSettingsRequest(BaseModel):
    mode: str
    previewTokens: int = 500


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


class McpServerRequest(BaseModel):
    id: str | None = None
    name: str
    transport: str = "http"
    url: str
    headers: dict[str, str] | None = None
    instructions: str = ""
    description: str = ""
    toolPrefix: str | None = None


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


@app.get("/api/conversations/{conversation_id}/session-info")
def get_session_info(conversation_id: str):
    """Inspect the live state the model sees for this conversation.

    Returns the fully composed system prompt (base + project knowledge +
    plugin instructions), plus the project/knowledge/plugin context that
    fed into it. Read-only.
    """
    convo = db.get_conversation(conversation_id)
    if convo is None:
        raise HTTPException(404, f"conversation not found: {conversation_id}")

    custom_prompt = None
    if convo.get("systemPromptId"):
        row = db.get_system_prompt(convo["systemPromptId"])
        if row:
            custom_prompt = {
                "id": row["id"],
                "name": row["name"],
                "content": row["content"],
            }

    project = None
    knowledge = None
    knowledge_links = None
    if convo.get("projectId"):
        project_row = db.get_project(convo["projectId"])
        if project_row:
            project = {
                "id": project_row["id"],
                "name": project_row["name"],
                "systemPromptId": project_row.get("systemPromptId"),
            }
            knowledge = db.expand_project_knowledge(convo["projectId"])
            knowledge_links = db.list_project_knowledge(convo["projectId"])

    base_prompt = custom_prompt["content"] if custom_prompt else BASE_SYSTEM_PROMPT
    composed = compose_system_prompt(
        base_prompt=base_prompt,
        conversation_id=conversation_id,
    )

    return {
        "conversation": convo,
        "model": get_active_model(),
        "basePrompt": {
            "isCustom": custom_prompt is not None,
            "name": custom_prompt["name"] if custom_prompt else "(default)",
            "content": base_prompt,
        },
        "project": project,
        "knowledge": knowledge,
        "knowledgeLinks": knowledge_links,
        "plugins": plugin_registry.list_plugin_status(conversation_id),
        "systemPrompt": composed,
        "systemPromptBytes": len(composed.encode("utf-8")),
        "systemPromptTokens": db.estimate_tokens(composed),
    }


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


@app.get("/api/projects/{project_id}/knowledge")
def get_project_knowledge(project_id: str):
    if db.get_project(project_id) is None:
        raise HTTPException(404, f"project not found: {project_id}")
    return {"links": db.list_project_knowledge(project_id)}


@app.post("/api/projects/{project_id}/knowledge")
def post_project_knowledge(project_id: str, req: ProjectKnowledgeRequest):
    if db.get_project(project_id) is None:
        raise HTTPException(404, f"project not found: {project_id}")
    try:
        link = db.add_project_knowledge(project_id, req.refType, req.refPath)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"link": link}


@app.delete("/api/projects/{project_id}/knowledge/{link_id}")
def delete_project_knowledge(project_id: str, link_id: str):
    if not db.remove_project_knowledge(project_id, link_id):
        raise HTTPException(404, "knowledge link not found")
    return {"ok": True}


@app.put("/api/projects/{project_id}/knowledge-settings")
def put_project_knowledge_settings(
    project_id: str, req: ProjectKnowledgeSettingsRequest
):
    if db.get_project(project_id) is None:
        raise HTTPException(404, f"project not found: {project_id}")
    try:
        project = db.set_project_knowledge_settings(project_id, req.mode, req.previewTokens)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"project": project}


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


# ---------- MCP servers ----------


def _normalize_mcp_id(raw: str | None, name: str) -> str:
    base = (raw or name or "server").strip().lower()
    base = re.sub(r"[^a-z0-9._-]+", "-", base).strip("-.") or "server"
    return base if base.startswith("mcp.") else f"mcp.{base}"


@app.get("/api/mcp-servers")
def get_mcp_servers():
    """List custom (DB-defined) MCP servers and the built-in presets."""
    return {
        "servers": db.list_mcp_servers(),
        "presets": [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "transport": p.mcp.transport if p.mcp else None,
                "url": p.mcp.url if p.mcp else None,
                "headers": p.mcp.headers if p.mcp else {},
                "configured": mcp_servers.is_configured(p),
            }
            for p in mcp_servers.PRESETS
        ],
    }


@app.post("/api/mcp-servers")
def post_mcp_server(req: McpServerRequest):
    if req.transport not in ("http", "sse"):
        raise HTTPException(400, f"unsupported transport: {req.transport}")
    if not req.url.strip():
        raise HTTPException(400, "url is required")
    server_id = _normalize_mcp_id(req.id, req.name)
    return db.upsert_mcp_server(
        server_id=server_id,
        name=req.name,
        transport=req.transport,
        url=req.url,
        headers=req.headers,
        instructions=req.instructions,
        description=req.description,
        tool_prefix=req.toolPrefix,
    )


@app.delete("/api/mcp-servers/{server_id}")
def delete_mcp_server_endpoint(server_id: str):
    if not db.delete_mcp_server(server_id):
        raise HTTPException(404, f"mcp server not found: {server_id}")
    return {"ok": True}


# ---------- Outlook (Microsoft Graph) auth ----------


@app.get("/api/outlook/status")
def get_outlook_status():
    return outlook_plugin.connection_status()


@app.post("/api/outlook/login")
async def post_outlook_login():
    if not outlook_plugin.is_configured():
        raise HTTPException(400, "OUTLOOK_CLIENT_ID not set; register an Entra app first")
    try:
        return await outlook_plugin.start_device_login()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"device login failed: {exc}")


@app.post("/api/outlook/login/poll")
async def post_outlook_login_poll():
    try:
        return await outlook_plugin.poll_device_login()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"login poll failed: {exc}")


@app.post("/api/outlook/disconnect")
def post_outlook_disconnect():
    outlook_plugin.disconnect()
    return {"ok": True}


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
async def upload(
    file: UploadFile,
    folder: str = "",
    conversationId: str | None = None,
):
    if folder:
        tools._safe_path(folder)
    raw = await file.read()
    name = Path(file.filename or "upload.bin").name
    content_type = file.content_type or "application/octet-stream"

    if conversationId or not content_type.startswith("text/"):
        target = tools.attachment_path(name, conversationId)
        target.write_bytes(raw)
        rel = tools.relative_workspace_path(target)
        extracted = tools.extract_text_for_attachment(target, content_type, raw)
        kind = tools._ext_kind(target)
        return db.upsert_attachment(
            path=rel,
            name=name,
            content_type=content_type,
            kind=kind,
            bytes_count=len(raw),
            extracted_text=extracted,
            conversation_id=conversationId,
        )

    rel = f"{folder.strip('/')}/{name}".strip("/")
    content = raw.decode("utf-8", errors="replace")
    return db.upsert_file(rel, content, tools._ext_kind(Path(name)))


@app.get("/api/attachments")
def get_attachments(conversationId: str | None = None):
    return {"attachments": db.list_attachments(conversationId)}


_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}


def _workspace_image_path(path: str) -> Path:
    raw = path.removeprefix("file://")
    if raw == "/workspace":
        return tools.WORKSPACE
    if raw.startswith("/workspace/"):
        return tools._safe_path(raw.removeprefix("/workspace/"))
    candidate = Path(raw)
    if candidate.is_absolute():
        try:
            return tools.remap_into_workspace(candidate)
        except ValueError as exc:
            raise HTTPException(400, f"path escapes workspace: {path}") from exc
    return tools._safe_path(raw)


@app.get("/api/workspace/image")
def get_workspace_image(path: str):
    p = _workspace_image_path(path)
    if not p.exists() or not p.is_file():
        raise HTTPException(404, f"file not found: {path}")
    if p.suffix.lower() not in _IMAGE_EXTS:
        raise HTTPException(400, f"not an image: {path}")
    mime, _ = mimetypes.guess_type(str(p))
    return FileResponse(str(p), media_type=mime or "application/octet-stream")


@app.get("/api/search")
def get_search(q: str, limit: int = 5, kind: str | None = None):
    return db.search_chunks(q, limit=min(limit, 20), kind_filter=kind)


class FileWriteRequest(BaseModel):
    path: str
    content: str


@app.put("/api/file")
def put_file(req: FileWriteRequest):
    result = tools.write_file(req.path, req.content)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


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
