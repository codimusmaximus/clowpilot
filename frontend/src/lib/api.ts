import type {
  AppMessage,
  Conversation,
  FileNode,
  ModelInfo,
  PluginStatus,
  Project,
  SystemPrompt,
} from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export async function fetchTree(): Promise<FileNode> {
  const res = await fetch(`${API_BASE}/api/tree`);
  if (!res.ok) throw new Error(`tree fetch failed: ${res.status}`);
  return res.json();
}

export async function fetchPageTree(): Promise<FileNode> {
  const res = await fetch(`${API_BASE}/api/pages/tree`);
  if (!res.ok) throw new Error(`page tree fetch failed: ${res.status}`);
  return res.json();
}

export async function fetchFileTree(): Promise<FileNode> {
  const res = await fetch(`${API_BASE}/api/files/tree`);
  if (!res.ok) throw new Error(`file tree fetch failed: ${res.status}`);
  return res.json();
}

export async function fetchFile(
  path: string
): Promise<{ path: string; content: string; kind: string; lines: number }> {
  const res = await fetch(
    `${API_BASE}/api/file?path=${encodeURIComponent(path)}`
  );
  if (!res.ok) throw new Error(`file fetch failed: ${res.status}`);
  return res.json();
}

export async function saveFile(path: string, content: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/file`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, content }),
  });
  if (!res.ok) throw new Error(`file save failed: ${res.status}`);
}

export async function uploadFile(file: File, folder = ""): Promise<void> {
  const fd = new FormData();
  fd.append("file", file);
  const url = `${API_BASE}/api/upload${
    folder ? `?folder=${encodeURIComponent(folder)}` : ""
  }`;
  const res = await fetch(url, { method: "POST", body: fd });
  if (!res.ok) throw new Error(`upload failed: ${res.status}`);
}

export async function fetchConversations(): Promise<{
  conversations: Conversation[];
  activeConversationId: string;
}> {
  const res = await fetch(`${API_BASE}/api/conversations`);
  if (!res.ok) throw new Error(`conversations fetch failed: ${res.status}`);
  return res.json();
}

export async function createConversation(
  title = "New chat",
  systemPromptId?: string | null,
  projectId?: string | null
): Promise<Conversation> {
  const res = await fetch(`${API_BASE}/api/conversations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title, systemPromptId, projectId }),
  });
  if (!res.ok) throw new Error(`conversation create failed: ${res.status}`);
  return res.json();
}

export async function deleteConversation(conversationId: string): Promise<void> {
  const res = await fetch(
    `${API_BASE}/api/conversations/${encodeURIComponent(conversationId)}`,
    { method: "DELETE" }
  );
  if (!res.ok) throw new Error(`conversation delete failed: ${res.status}`);
}

export async function fetchProjects(): Promise<Project[]> {
  const res = await fetch(`${API_BASE}/api/projects`);
  if (!res.ok) throw new Error(`projects fetch failed: ${res.status}`);
  const data = (await res.json()) as { projects: Project[] };
  return data.projects;
}

export async function createProject(
  name: string,
  systemPromptId?: string | null
): Promise<Project> {
  const res = await fetch(`${API_BASE}/api/projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, systemPromptId }),
  });
  if (!res.ok) throw new Error(`project create failed: ${res.status}`);
  return res.json();
}

export async function deleteProject(projectId: string): Promise<void> {
  const res = await fetch(
    `${API_BASE}/api/projects/${encodeURIComponent(projectId)}`,
    { method: "DELETE" }
  );
  if (!res.ok) throw new Error(`project delete failed: ${res.status}`);
}

export async function fetchMessages(
  conversationId: string
): Promise<{ messages: AppMessage[]; headId: string | null }> {
  const res = await fetch(
    `${API_BASE}/api/conversations/${encodeURIComponent(conversationId)}/messages`
  );
  if (!res.ok) throw new Error(`messages fetch failed: ${res.status}`);
  const data = (await res.json()) as { messages: AppMessage[]; headId?: string | null };
  return { messages: data.messages, headId: data.headId ?? null };
}

export async function saveMessages(
  conversationId: string,
  messages: AppMessage[],
  headId: string | null,
): Promise<void> {
  const res = await fetch(
    `${API_BASE}/api/conversations/${encodeURIComponent(conversationId)}/messages`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages, headId }),
    }
  );
  if (!res.ok) throw new Error(`messages save failed: ${res.status}`);
}

export async function fetchSystemPrompts(): Promise<{
  prompts: SystemPrompt[];
  activeSystemPromptId: string;
}> {
  const res = await fetch(`${API_BASE}/api/system-prompts`);
  if (!res.ok) throw new Error(`system prompts fetch failed: ${res.status}`);
  return res.json();
}

export async function createSystemPrompt(
  name: string,
  content: string
): Promise<SystemPrompt> {
  const res = await fetch(`${API_BASE}/api/system-prompts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, content }),
  });
  if (!res.ok) throw new Error(`system prompt create failed: ${res.status}`);
  return res.json();
}

export async function updateSystemPrompt(
  id: string,
  name: string,
  content: string
): Promise<SystemPrompt> {
  const res = await fetch(
    `${API_BASE}/api/system-prompts/${encodeURIComponent(id)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, content }),
    }
  );
  if (!res.ok) throw new Error(`system prompt update failed: ${res.status}`);
  return res.json();
}

export async function setActiveSystemPrompt(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/system-prompts/active`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id }),
  });
  if (!res.ok) throw new Error(`system prompt select failed: ${res.status}`);
}

export async function setConversationSystemPrompt(
  conversationId: string,
  id: string
): Promise<Conversation> {
  const res = await fetch(
    `${API_BASE}/api/conversations/${encodeURIComponent(conversationId)}/system-prompt`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id }),
    }
  );
  if (!res.ok) throw new Error(`conversation prompt select failed: ${res.status}`);
  return res.json();
}

export async function fetchPlugins(): Promise<PluginStatus[]> {
  const res = await fetch(`${API_BASE}/api/plugins`);
  if (!res.ok) throw new Error(`plugins fetch failed: ${res.status}`);
  const data = (await res.json()) as { plugins: PluginStatus[] };
  return data.plugins;
}

export async function fetchConversationPlugins(
  conversationId: string
): Promise<PluginStatus[]> {
  const res = await fetch(
    `${API_BASE}/api/conversations/${encodeURIComponent(conversationId)}/plugins`
  );
  if (!res.ok) throw new Error(`conversation plugins fetch failed: ${res.status}`);
  const data = (await res.json()) as { plugins: PluginStatus[] };
  return data.plugins;
}

export async function toggleConversationPlugin(
  conversationId: string,
  pluginId: string,
  enabled: boolean
): Promise<void> {
  const res = await fetch(
    `${API_BASE}/api/conversations/${encodeURIComponent(
      conversationId
    )}/plugins/${encodeURIComponent(pluginId)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    }
  );
  if (!res.ok) throw new Error(`plugin toggle failed: ${res.status}`);
}

export async function toggleConversationTool(
  conversationId: string,
  pluginId: string,
  toolName: string,
  enabled: boolean
): Promise<void> {
  const res = await fetch(
    `${API_BASE}/api/conversations/${encodeURIComponent(conversationId)}/plugins/${encodeURIComponent(pluginId)}/tools/${encodeURIComponent(toolName)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    }
  );
  if (!res.ok) throw new Error(`tool toggle failed: ${res.status}`);
}

export async function fetchModels(): Promise<{
  models: ModelInfo[];
  activeModel: string;
}> {
  const res = await fetch(`${API_BASE}/api/models`);
  if (!res.ok) throw new Error(`models fetch failed: ${res.status}`);
  return res.json();
}

export async function setActiveModel(model: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/models/active`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model }),
  });
  if (!res.ok) throw new Error(`model select failed: ${res.status}`);
}

export const CHAT_URL = `${API_BASE}/api/chat`;
