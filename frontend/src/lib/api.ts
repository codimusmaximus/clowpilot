import type {
  AttachmentRecord,
  AppMessage,
  Conversation,
  FileNode,
  ModelInfo,
  PluginStatus,
  McpServer,
  McpPreset,
  Project,
  SystemPrompt,
  UploadedAttachment,
} from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export function workspaceImageUrl(path: string): string {
  return `/api/workspace/image?path=${encodeURIComponent(path)}`;
}

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

export async function uploadAttachment(
  file: File,
  conversationId?: string | null,
): Promise<UploadedAttachment> {
  const fd = new FormData();
  fd.append("file", file);
  const query = conversationId
    ? `?conversationId=${encodeURIComponent(conversationId)}`
    : "";
  const res = await fetch(`${API_BASE}/api/upload${query}`, {
    method: "POST",
    body: fd,
  });
  if (!res.ok) throw new Error(`attachment upload failed: ${res.status}`);
  return res.json();
}

export async function fetchAttachments(
  conversationId?: string | null,
): Promise<UploadedAttachment[]> {
  const query = conversationId
    ? `?conversationId=${encodeURIComponent(conversationId)}`
    : "";
  const res = await fetch(`${API_BASE}/api/attachments${query}`);
  if (!res.ok) throw new Error(`attachments fetch failed: ${res.status}`);
  const data = (await res.json()) as { attachments: UploadedAttachment[] };
  return data.attachments;
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

export async function renameProject(
  projectId: string,
  name: string
): Promise<Project> {
  const res = await fetch(
    `${API_BASE}/api/projects/${encodeURIComponent(projectId)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }
  );
  if (!res.ok) throw new Error(`project rename failed: ${res.status}`);
  return res.json();
}

export async function deleteProject(projectId: string): Promise<void> {
  const res = await fetch(
    `${API_BASE}/api/projects/${encodeURIComponent(projectId)}`,
    { method: "DELETE" }
  );
  if (!res.ok) throw new Error(`project delete failed: ${res.status}`);
}

export async function setConversationProject(
  conversationId: string,
  projectId: string | null
): Promise<void> {
  const res = await fetch(
    `${API_BASE}/api/conversations/${encodeURIComponent(conversationId)}/project`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ projectId }),
    }
  );
  if (!res.ok) throw new Error(`move conversation failed: ${res.status}`);
}

export type ProjectKnowledgeRefType = "page" | "page_folder";

export interface ProjectKnowledgeLink {
  id: string;
  project_id: string;
  ref_type: ProjectKnowledgeRefType;
  ref_path: string;
  created_at: number;
}

export async function fetchProjectKnowledge(
  projectId: string
): Promise<ProjectKnowledgeLink[]> {
  const res = await fetch(
    `${API_BASE}/api/projects/${encodeURIComponent(projectId)}/knowledge`
  );
  if (!res.ok) throw new Error(`knowledge fetch failed: ${res.status}`);
  const data = (await res.json()) as { links: ProjectKnowledgeLink[] };
  return data.links;
}

export async function addProjectKnowledge(
  projectId: string,
  refType: ProjectKnowledgeRefType,
  refPath: string
): Promise<ProjectKnowledgeLink> {
  const res = await fetch(
    `${API_BASE}/api/projects/${encodeURIComponent(projectId)}/knowledge`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refType, refPath }),
    }
  );
  if (!res.ok) throw new Error(`knowledge add failed: ${res.status}`);
  const data = (await res.json()) as { link: ProjectKnowledgeLink };
  return data.link;
}

export async function updateProjectKnowledgeSettings(
  projectId: string,
  mode: "full" | "preview" | "metadata",
  previewTokens: number
): Promise<Project> {
  const res = await fetch(
    `${API_BASE}/api/projects/${encodeURIComponent(projectId)}/knowledge-settings`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode, previewTokens }),
    }
  );
  if (!res.ok) throw new Error(`knowledge settings update failed: ${res.status}`);
  const data = (await res.json()) as { project: Project };
  return data.project;
}

export async function removeProjectKnowledge(
  projectId: string,
  linkId: string
): Promise<void> {
  const res = await fetch(
    `${API_BASE}/api/projects/${encodeURIComponent(projectId)}/knowledge/${encodeURIComponent(linkId)}`,
    { method: "DELETE" }
  );
  if (!res.ok) throw new Error(`knowledge remove failed: ${res.status}`);
}

export interface SessionInfo {
  conversation: {
    id: string;
    title: string;
    systemPromptId: string | null;
    projectId: string | null;
  };
  model: string;
  basePrompt: { isCustom: boolean; name: string; content: string };
  project: { id: string; name: string; systemPromptId: string | null } | null;
  knowledge:
    | {
        included: { ref_type: string; ref_path: string; tokens: number; bytes: number; from_folder?: string; preview_clipped?: boolean }[];
        truncated: { ref_type: string; ref_path: string; tokens: number; reason: string; from_folder?: string }[];
        total_tokens: number;
        max_tokens: number;
        mode: "full" | "preview" | "metadata";
        preview_tokens: number;
      }
    | null;
  knowledgeLinks: ProjectKnowledgeLink[] | null;
  plugins: PluginStatus[];
  systemPrompt: string;
  systemPromptBytes: number;
  systemPromptTokens: number;
}

export async function fetchSessionInfo(
  conversationId: string
): Promise<SessionInfo> {
  const res = await fetch(
    `${API_BASE}/api/conversations/${encodeURIComponent(conversationId)}/session-info`
  );
  if (!res.ok) throw new Error(`session info fetch failed: ${res.status}`);
  return res.json();
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

export function uploadedAttachmentToRecord(
  attachment: UploadedAttachment,
): AttachmentRecord {
  const contentType = attachment.contentType || "application/octet-stream";
  const name = attachment.name || attachment.path || "attachment";
  const path = attachment.path || "";
  return {
    id: attachment.id,
    type: contentType.startsWith("image/") ? "image" : "document",
    name,
    contentType,
    path,
    content: [
      {
        type: "file",
        data: path,
        mimeType: contentType,
        filename: name,
      },
    ],
    status: { type: "complete" },
  };
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

export async function fetchMcpServers(): Promise<{
  servers: McpServer[];
  presets: McpPreset[];
}> {
  const res = await fetch(`${API_BASE}/api/mcp-servers`);
  if (!res.ok) throw new Error(`mcp servers fetch failed: ${res.status}`);
  return res.json();
}

export async function saveMcpServer(input: {
  id?: string;
  name: string;
  transport?: string;
  url: string;
  headers?: Record<string, string>;
  instructions?: string;
  description?: string;
  toolPrefix?: string | null;
}): Promise<McpServer> {
  const res = await fetch(`${API_BASE}/api/mcp-servers`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new Error(`mcp server save failed: ${res.status}`);
  return res.json();
}

export async function deleteMcpServer(serverId: string): Promise<void> {
  const res = await fetch(
    `${API_BASE}/api/mcp-servers/${encodeURIComponent(serverId)}`,
    { method: "DELETE" }
  );
  if (!res.ok) throw new Error(`mcp server delete failed: ${res.status}`);
}

export type OutlookStatus = {
  configured: boolean;
  connected: boolean;
  account: string | null;
  pending: boolean;
};

export type OutlookLogin = {
  userCode: string;
  verificationUri: string;
  message: string;
  expiresIn: number;
  interval: number;
};

export type OutlookPoll = {
  status: "idle" | "pending" | "connected" | "expired" | "error";
  account?: string | null;
  interval?: number;
  error?: string;
  detail?: string;
};

export async function fetchOutlookStatus(): Promise<OutlookStatus> {
  const res = await fetch(`${API_BASE}/api/outlook/status`);
  if (!res.ok) throw new Error(`outlook status failed: ${res.status}`);
  return res.json();
}

export async function startOutlookLogin(): Promise<OutlookLogin> {
  const res = await fetch(`${API_BASE}/api/outlook/login`, { method: "POST" });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || `outlook login failed: ${res.status}`);
  }
  return res.json();
}

export async function pollOutlookLogin(): Promise<OutlookPoll> {
  const res = await fetch(`${API_BASE}/api/outlook/login/poll`, { method: "POST" });
  if (!res.ok) throw new Error(`outlook poll failed: ${res.status}`);
  return res.json();
}

export async function disconnectOutlook(): Promise<void> {
  const res = await fetch(`${API_BASE}/api/outlook/disconnect`, { method: "POST" });
  if (!res.ok) throw new Error(`outlook disconnect failed: ${res.status}`);
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
