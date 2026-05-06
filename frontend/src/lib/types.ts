export type ToolName =
  | "list_tree"
  | "read_file"
  | "write_file"
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
