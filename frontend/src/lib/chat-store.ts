"use client";

import { create } from "zustand";
import {
  CHAT_URL,
  createConversation as createConversationApi,
  createProject as createProjectApi,
  createSystemPrompt as createSystemPromptApi,
  deleteConversation as deleteConversationApi,
  deleteProject as deleteProjectApi,
  fetchConversations,
  fetchFile,
  fetchMessages,
  fetchModels,
  fetchProjects,
  fetchSystemPrompts,
  uploadedAttachmentToRecord,
  uploadAttachment,
  workspaceImageUrl,
  saveMessages,
  setActiveModel as setActiveModelApi,
  setConversationSystemPrompt,
  updateSystemPrompt as updateSystemPromptApi,
} from "./api";
import { useWorkspace } from "./workspace-store";
import type {
  AttachmentRecord,
  AppMessage,
  Conversation,
  ModelInfo,
  PluginStatus,
  Project,
  SystemPrompt,
  TextPart,
  ToolCallPart,
} from "./types";

type ChatState = {
  messages: AppMessage[];
  headId: string | null;
  conversations: Conversation[];
  activeConversationId: string | null;
  systemPrompts: SystemPrompt[];
  activeSystemPromptId: string | null;
  isRunning: boolean;
  plugins: PluginStatus[];
  projects: Project[];
  models: ModelInfo[];
  activeModel: string | null;
  selectModel: (model: string) => Promise<void>;
  load: () => Promise<void>;
  newConversation: (projectId?: string | null) => Promise<void>;
  newConversationInProject: (projectId: string) => Promise<void>;
  deleteConversation: (id: string) => Promise<void>;
  selectConversation: (id: string) => Promise<void>;
  selectSystemPrompt: (id: string) => Promise<void>;
  createSystemPrompt: (name: string, content: string) => Promise<void>;
  updateSystemPrompt: (id: string, name: string, content: string) => Promise<void>;
  fetchPlugins: () => Promise<void>;
  togglePlugin: (pluginId: string, enabled: boolean) => Promise<void>;
  toggleTool: (pluginId: string, toolName: string, enabled: boolean) => Promise<void>;
  createProject: (name: string, systemPromptId?: string | null) => Promise<void>;
  deleteProject: (id: string) => Promise<void>;
  send: (text: string, parentId: string | null, attachments?: AttachmentRecord[]) => Promise<void>;
  editMessage: (sourceId: string | null, text: string, parentId: string | null, attachments?: AttachmentRecord[]) => Promise<void>;
  setHeadId: (headId: string | null) => void;
  stopGeneration: () => void;
};

let _abortController: AbortController | null = null;

const newId = () =>
  `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;

const PRINTABLE_LANGS = new Set([
  "markdown",
  "python",
  "typescript",
  "javascript",
  "json",
  "yaml",
  "css",
  "html",
  "bash",
  "csv",
  "sql",
  "go",
  "rust",
  "text",
]);

function applyToolToWorkspace(name: string, result: unknown) {
  if (!result || typeof result !== "object") return;
  const r = result as Record<string, unknown>;
  if (r.error) return;

  const ws = useWorkspace.getState();

  switch (name) {
    // workspace UI tools (new names) + old names for back-compat
    case "display":
    case "display_file": {
      const { path, content, kind } = r as { path: string; content: string; kind: string };
      ws.openFile(path, content, PRINTABLE_LANGS.has(kind) ? kind : "text");
      break;
    }
    case "page_write":
    case "write_file": {
      const { path, content, kind } = r as { path: string; content: string; kind: string };
      ws.openFile(path, content, PRINTABLE_LANGS.has(kind) ? kind : "text");
      break;
    }
    case "page_patch":
    case "page_patch_lines":
    case "replace_in_file":
    case "replace_file_lines": {
      const { path, content, kind } = r as { path: string; content: string; kind: string };
      if (path && content !== undefined) {
        ws.openFile(path, content, PRINTABLE_LANGS.has(kind) ? kind : "text");
      }
      break;
    }
    case "page_move":
    case "move_path": {
      const { source, destination } = r as { source: string; destination: string };
      const affected = ws.tabs.filter(
        (t) => t.kind === "file" && (t.path === source || t.path.startsWith(`${source}/`))
      );
      for (const tab of affected) {
        if (tab.kind !== "file") continue;
        const newPath = destination + tab.path.slice(source.length);
        ws.closeFile(tab.path);
        fetchFile(newPath)
          .then((f) => useWorkspace.getState().openFile(f.path, f.content, f.kind))
          .catch(() => undefined);
      }
      break;
    }
    case "page_delete":
    case "delete_file": {
      const deletedPaths = Array.isArray(r.deleted_paths)
        ? r.deleted_paths
        : typeof r.path === "string"
          ? [r.path]
          : [];
      for (const path of deletedPaths) {
        if (typeof path === "string") ws.closeFile(path);
      }
      break;
    }
    case "highlight": {
      const { path, start_line, end_line, comment } = r as {
        path: string;
        start_line: number;
        end_line: number;
        comment: string;
      };
      const tabId = `file:${path}`;
      const isOpen = ws.tabs.some((t) => t.id === tabId);
      if (!isOpen) {
        // auto-open the file so the user actually sees the highlight
        fetchFile(path)
          .then((f) => {
            const wsLatest = useWorkspace.getState();
            const lang = PRINTABLE_LANGS.has(f.kind) ? f.kind : "text";
            wsLatest.openFile(f.path, f.content, lang);
            wsLatest.addHighlight({
              path,
              startLine: start_line,
              endLine: end_line,
              comment,
            });
            wsLatest.setActive(tabId);
          })
          .catch(() => {
            ws.addHighlight({
              path,
              startLine: start_line,
              endLine: end_line,
              comment,
            });
          });
      } else {
        ws.addHighlight({
          path,
          startLine: start_line,
          endLine: end_line,
          comment,
        });
        ws.setActive(tabId);
      }
      break;
    }
    case "display_image": {
      const { path } = r as { path: string };
      const url = workspaceImageUrl(path);
      ws.openImage(path, url);
      break;
    }
    case "snippet": {
      const { content, format } = r as {
        content: string;
        format: "markdown" | "html";
      };
      ws.openSnippet(content, format);
      break;
    }
  }
}

function ensureTextPart(parts: AppMessage["parts"]): TextPart {
  const last = parts[parts.length - 1];
  if (last && last.type === "text") return last;
  const t: TextPart = { type: "text", text: "" };
  parts.push(t);
  return t;
}

function buildPath(messages: AppMessage[], targetId: string | null): AppMessage[] {
  if (!targetId) return [];
  const byId = new Map(messages.map((m) => [m.id, m]));
  const path: AppMessage[] = [];
  let current = byId.get(targetId);
  while (current) {
    path.unshift(current);
    current = current.parentId ? byId.get(current.parentId) : undefined;
  }
  return path;
}

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  headId: null,
  conversations: [],
  activeConversationId: null,
  systemPrompts: [],
  activeSystemPromptId: null,
  isRunning: false,
  plugins: [],
  projects: [],
  models: [],
  activeModel: null,

  selectModel: async (model) => {
    await setActiveModelApi(model);
    set({ activeModel: model });
  },

  load: async () => {
    if (get().isRunning) return;
    const [{ conversations, activeConversationId }, prompts, projects, { models, activeModel }] =
      await Promise.all([
        fetchConversations(),
        fetchSystemPrompts(),
        fetchProjects(),
        fetchModels(),
      ]);
    const { messages, headId } = await fetchMessages(activeConversationId);
    const activeConversation = conversations.find((c) => c.id === activeConversationId);
    set({
      conversations,
      activeConversationId,
      messages,
      headId,
      systemPrompts: prompts.prompts,
      activeSystemPromptId:
        activeConversation?.systemPromptId ?? prompts.activeSystemPromptId,
      projects,
      models,
      activeModel,
    });
    await get().fetchPlugins();
  },

  newConversation: async (projectId?: string | null) => {
    if (get().isRunning) return;
    const conversation = await createConversationApi(
      "New chat",
      get().activeSystemPromptId,
      projectId
    );
    set((s) => ({
      conversations: [conversation, ...s.conversations],
      activeConversationId: conversation.id,
      activeSystemPromptId: conversation.systemPromptId ?? s.activeSystemPromptId,
      messages: [],
      headId: null,
    }));
    await get().fetchPlugins();
  },

  newConversationInProject: async (projectId: string) => {
    if (get().isRunning) return;
    const project = get().projects.find((p) => p.id === projectId);
    const systemPromptId = project?.systemPromptId ?? get().activeSystemPromptId;
    const conversation = await createConversationApi("New chat", systemPromptId, projectId);
    set((s) => ({
      conversations: [conversation, ...s.conversations],
      activeConversationId: conversation.id,
      activeSystemPromptId: conversation.systemPromptId ?? s.activeSystemPromptId,
      messages: [],
      headId: null,
    }));
    await get().fetchPlugins();
  },

  deleteConversation: async (id: string) => {
    await deleteConversationApi(id);
    const s = get();
    const remaining = s.conversations.filter((c) => c.id !== id);
    if (s.activeConversationId === id) {
      const next = remaining[0];
      if (next) {
        const { messages, headId } = await fetchMessages(next.id);
        set({
          conversations: remaining,
          activeConversationId: next.id,
          activeSystemPromptId: next.systemPromptId ?? s.activeSystemPromptId,
          messages,
          headId,
        });
      } else {
        set({ conversations: remaining, activeConversationId: null, messages: [], headId: null });
      }
    } else {
      set({ conversations: remaining });
    }
  },

  selectConversation: async (id) => {
    if (get().isRunning || get().activeConversationId === id) return;
    const { messages, headId } = await fetchMessages(id);
    const conversation = get().conversations.find((c) => c.id === id);
    set({
      activeConversationId: id,
      activeSystemPromptId:
        conversation?.systemPromptId ?? get().activeSystemPromptId,
      messages,
      headId,
    });
    await get().fetchPlugins();
  },

  selectSystemPrompt: async (id) => {
    const conversationId = get().activeConversationId;
    if (!conversationId) return;
    const conversation = await setConversationSystemPrompt(conversationId, id);
    set({ activeSystemPromptId: id });
    set((s) => ({
      conversations: s.conversations.map((c) =>
        c.id === conversation.id ? conversation : c
      ),
    }));
  },

  createSystemPrompt: async (name, content) => {
    const prompt = await createSystemPromptApi(name, content);
    const conversationId = get().activeConversationId;
    const conversation = conversationId
      ? await setConversationSystemPrompt(conversationId, prompt.id)
      : null;
    set((s) => ({
      systemPrompts: [prompt, ...s.systemPrompts],
      activeSystemPromptId: prompt.id,
      conversations: conversation
        ? s.conversations.map((c) => (c.id === conversation.id ? conversation : c))
        : s.conversations,
    }));
  },

  updateSystemPrompt: async (id, name, content) => {
    const prompt = await updateSystemPromptApi(id, name, content);
    set((s) => ({
      systemPrompts: s.systemPrompts.map((p) => (p.id === id ? prompt : p)),
    }));
  },

  fetchPlugins: async () => {
    const conversationId = get().activeConversationId;
    if (!conversationId) return;
    try {
      const { fetchConversationPlugins } = await import("./api");
      const plugins = await fetchConversationPlugins(conversationId);
      set({ plugins });
    } catch (err) {
      console.error("fetchPlugins failed", err);
    }
  },

  togglePlugin: async (pluginId, enabled) => {
    const conversationId = get().activeConversationId;
    if (!conversationId) return;
    try {
      const { toggleConversationPlugin } = await import("./api");
      await toggleConversationPlugin(conversationId, pluginId, enabled);
      set((s) => ({
        plugins: s.plugins.map((p) =>
          p.id === pluginId ? { ...p, enabled } : p
        ),
      }));
    } catch (err) {
      console.error("togglePlugin failed", err);
    }
  },

  toggleTool: async (pluginId, toolName, enabled) => {
    const conversationId = get().activeConversationId;
    if (!conversationId) return;
    try {
      const { toggleConversationTool } = await import("./api");
      await toggleConversationTool(conversationId, pluginId, toolName, enabled);
      set((s) => ({
        plugins: s.plugins.map((p) =>
          p.id === pluginId
            ? { ...p, toolsEnabled: { ...p.toolsEnabled, [toolName]: enabled } }
            : p
        ),
      }));
    } catch (err) {
      console.error("toggleTool failed", err);
    }
  },

  createProject: async (name, systemPromptId) => {
    const project = await createProjectApi(name, systemPromptId);
    set((s) => ({ projects: [...s.projects, project] }));
  },

  deleteProject: async (id) => {
    await deleteProjectApi(id);
    set((s) => ({
      projects: s.projects.filter((p) => p.id !== id),
      conversations: s.conversations.map((c) =>
        c.projectId === id ? { ...c, projectId: null } : c
      ),
    }));
  },

  setHeadId: (headId) => set({ headId }),
  stopGeneration: () => { _abortController?.abort(); },

  editMessage: async (_sourceId, text, parentId, attachments) => {
    await get().send(text, parentId, attachments);
  },

  send: async (text: string, parentId: string | null, attachments?: AttachmentRecord[]) => {
    if ((!text.trim() && !(attachments && attachments.length)) || get().isRunning) return;
    let conversationId = get().activeConversationId;
    if (!conversationId) {
      const conversation = await createConversationApi(
        "New chat",
        get().activeSystemPromptId
      );
      conversationId = conversation.id;
      set((s) => ({
        conversations: [conversation, ...s.conversations],
        activeConversationId: conversation.id,
        activeSystemPromptId: conversation.systemPromptId ?? s.activeSystemPromptId,
      }));
    }

    const userMsg: AppMessage = {
      id: newId(),
      role: "user",
      parts: [{ type: "text", text }],
      attachments,
      createdAt: Date.now(),
      parentId,
    };
    const assistantMsg: AppMessage = {
      id: newId(),
      role: "assistant",
      parts: [],
      createdAt: Date.now(),
      parentId: userMsg.id,
    };

    set((s) => ({
      messages: [...s.messages, userMsg, assistantMsg],
      headId: assistantMsg.id,
      isRunning: true,
    }));

    const historyPath = buildPath(get().messages, parentId);
    const payload = {
      conversationId,
      systemPromptId: get().activeSystemPromptId,
      messages: [...historyPath, userMsg].map((m) => ({
        role: m.role,
        content:
          m.role === "user" && m.parts.length === 1 && m.parts[0].type === "text"
            ? m.parts[0].text
            : m.parts.map((p) =>
                p.type === "text"
                  ? { type: "text", text: p.text }
                  : {
                      type: "tool-call",
                      id: p.toolCallId,
                      name: p.toolName,
                      input: p.args ?? {},
                      result: p.result ?? null,
                    }
              ),
        attachments: m.attachments,
      })),
    };

    const updateAssistant = (mut: (m: AppMessage) => void) => {
      set((s) => ({
        messages: s.messages.map((m) => {
          if (m.id !== assistantMsg.id) return m;
          const copy: AppMessage = { ...m, parts: [...m.parts] };
          mut(copy);
          return copy;
        }),
      }));
    };

    try {
      _abortController = new AbortController();
      const res = await fetch(CHAT_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: _abortController.signal,
      });
      if (!res.ok || !res.body) throw new Error(`chat failed: ${res.status}`);

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });

        let idx;
        while ((idx = buf.indexOf("\n\n")) !== -1) {
          const chunk = buf.slice(0, idx);
          buf = buf.slice(idx + 2);
          const line = chunk.split("\n").find((l) => l.startsWith("data:"));
          if (!line) continue;
          const json = line.slice(5).trim();
          if (!json) continue;
          let event: Record<string, unknown>;
          try {
            event = JSON.parse(json);
          } catch {
            continue;
          }
          handleEvent(event, updateAssistant);
        }
      }
    } catch (err) {
      const aborted = (err as Error).name === "AbortError";
      if (!aborted) {
        updateAssistant((m) => {
          m.parts.push({ type: "text", text: `\n\n_⚠ ${(err as Error).message}_` });
        });
      }
    } finally {
      _abortController = null;
      set({ isRunning: false });
      await saveMessages(conversationId, get().messages, get().headId).catch(() => undefined);
      const { conversations } = await fetchConversations().catch(() => ({
        conversations: get().conversations,
      }));
      set({ conversations });
    }
  },
}));

function handleEvent(
  event: Record<string, unknown>,
  updateAssistant: (mut: (m: AppMessage) => void) => void
) {
  switch (event.type) {
    case "text-delta": {
      const delta = String(event.delta ?? "");
      updateAssistant((m) => {
        const tp = ensureTextPart(m.parts);
        tp.text += delta;
      });
      break;
    }
    case "tool-call-start": {
      const id = String(event.id);
      const name = String(event.name);
      updateAssistant((m) => {
        m.parts.push({
          type: "tool-call",
          toolCallId: id,
          toolName: name,
          argsText: "",
          status: "streaming",
        });
      });
      break;
    }
    case "tool-call-input-delta": {
      const id = String(event.id);
      const delta = String(event.delta ?? "");
      updateAssistant((m) => {
        const tc = m.parts.find(
          (p): p is ToolCallPart =>
            p.type === "tool-call" && p.toolCallId === id
        );
        if (tc) tc.argsText = (tc.argsText ?? "") + delta;
      });
      break;
    }
    case "tool-call-input": {
      const id = String(event.id);
      const input = event.input as Record<string, unknown>;
      updateAssistant((m) => {
        const tc = m.parts.find(
          (p): p is ToolCallPart =>
            p.type === "tool-call" && p.toolCallId === id
        );
        if (tc) {
          tc.args = input;
          tc.status = "executing";
        }
      });
      break;
    }
    case "tool-result": {
      const id = String(event.id);
      const name = String(event.name);
      const result = event.result;
      updateAssistant((m) => {
        const tc = m.parts.find(
          (p): p is ToolCallPart =>
            p.type === "tool-call" && p.toolCallId === id
        );
        if (tc) {
          tc.result = result;
          tc.status =
            result &&
            typeof result === "object" &&
            "error" in (result as Record<string, unknown>)
              ? "error"
              : "done";
        }
      });
      applyToolToWorkspace(name, result);
      break;
    }
    case "error": {
      updateAssistant((m) => {
        m.parts.push({
          type: "text",
          text: `\n\n_⚠ ${event.message}_`,
        });
      });
      break;
    }
    case "model-switch": {
      // Backend auto-switched providers due to quota; update the active model in state
      const to = String(event.to ?? "");
      if (to) useChatStore.setState({ activeModel: to });
      break;
    }
    case "done":
      break;
  }
}
