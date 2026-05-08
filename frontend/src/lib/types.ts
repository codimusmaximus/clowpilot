export type ToolName =
  | "list_tree"
  | "create_folder"
  | "read_file"
  | "write_file"
  | "replace_in_file"
  | "replace_file_lines"
  | "delete_file"
  | "display_file"
  | "highlight"
  | "snippet";

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

export type AppMessage = {
  id: string;
  role: "user" | "assistant";
  parts: Array<TextPart | ToolCallPart>;
  createdAt: number;
  parentId: string | null;
};

export type Conversation = {
  id: string;
  title: string;
  systemPromptId: string | null;
  createdAt: number;
  updatedAt: number;
};

export type SystemPrompt = {
  id: string;
  name: string;
  content: string;
  createdAt: number;
  updatedAt: number;
};

export type PluginStatus = {
  id: string;
  name: string;
  type: "core" | "external";
  enabled: boolean;
  config: Record<string, unknown>;
  configSchema: Record<string, unknown> | null;
  tools: string[];
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

export type Tab = FileTab | SnippetTab;
