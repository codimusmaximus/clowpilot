import type { CompleteAttachment, FileMessagePart } from "@assistant-ui/react";

export type ToolName =
  | "list_tree"
  | "create_folder"
  | "read_file"
  | "write_file"
  | "replace_in_file"
  | "replace_file_lines"
  | "delete_file"
  | "display_file"
  | "display_image"
  | "highlight"
  | "snippet"
  | "search";

export type ToolCallStatus = "streaming" | "ready" | "executing" | "done" | "error";

export type ToolCallPart = {
  type: "tool-call";
  toolCallId: string;
  toolName: ToolName | string;
  argsText?: string;
  args?: Record<string, unknown>;
  result?: unknown;
  status: ToolCallStatus;
};

export type TextPart = { type: "text"; text: string };

export type AttachmentContentPart = FileMessagePart;

export type AttachmentRecord = Omit<CompleteAttachment, "content"> & {
  path?: string;
  content: AttachmentContentPart[];
};

export type AppMessage = {
  id: string;
  role: "user" | "assistant";
  parts: Array<TextPart | ToolCallPart>;
  attachments?: AttachmentRecord[];
  createdAt: number;
  parentId: string | null;
};

export type Conversation = {
  id: string;
  title: string;
  systemPromptId: string | null;
  projectId: string | null;
  createdAt: number;
  updatedAt: number;
};

export type KnowledgeMode = "full" | "preview" | "metadata";

export type Project = {
  id: string;
  name: string;
  systemPromptId: string | null;
  createdAt: number;
  updatedAt: number;
  knowledgeMode: KnowledgeMode;
  knowledgePreviewTokens: number;
};

export type SystemPrompt = {
  id: string;
  name: string;
  content: string;
  createdAt: number;
  updatedAt: number;
};

export type ModelInfo = {
  id: string;
  name: string;
  model: string;
};

export type UploadedAttachment = {
  id: string;
  path: string;
  name: string;
  contentType: string;
  kind: string;
  bytes: number;
  createdAt: number;
  updatedAt: number;
};

export type PluginStatus = {
  id: string;
  name: string;
  type: "core" | "external";
  enabled: boolean;
  description?: string;
  config: Record<string, unknown>;
  configSchema: Record<string, unknown> | null;
  tools: string[];
  toolsEnabled?: Record<string, boolean>;
};

export type FileNode = {
  name: string;
  path: string;
  type: "file" | "dir";
  kind?: string;
  size?: number;
  children?: FileNode[];
};

export type Highlight = {
  id: string;
  path: string;
  startLine: number;
  endLine: number;
  comment: string;
  createdAt: number;
};

export type FileTab = {
  id: string;
  kind: "file";
  path: string;
  content: string;
  language: string;
  openedAt: number;
};

export type SnippetTab = {
  id: string;
  kind: "snippet";
  format: "markdown" | "html";
  content: string;
  title: string;
  openedAt: number;
};

export type ImageTab = {
  id: string;
  kind: "image";
  path: string;
  url: string;
  openedAt: number;
};

export type Tab = FileTab | SnippetTab | ImageTab;
