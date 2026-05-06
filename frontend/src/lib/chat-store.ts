"use client";

import { create } from "zustand";
import { CHAT_URL, fetchFile } from "./api";
import { useWorkspace } from "./workspace-store";
import type { AppMessage, TextPart, ToolCallPart } from "./types";

type ChatState = {
  messages: AppMessage[];
  isRunning: boolean;
  send: (text: string) => Promise<void>;
};

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
    case "display_file": {
      const { path, content, kind } = r as {
        path: string;
        content: string;
        kind: string;
      };
      const lang = PRINTABLE_LANGS.has(kind) ? kind : "text";
      ws.openFile(path, content, lang);
      break;
    }
    case "write_file": {
      const { path, content, kind } = r as {
        path: string;
        content: string;
        kind: string;
      };
      const lang = PRINTABLE_LANGS.has(kind) ? kind : "text";
      ws.openFile(path, content, lang);
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

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  isRunning: false,

  send: async (text: string) => {
    if (!text.trim() || get().isRunning) return;

    const userMsg: AppMessage = {
      id: newId(),
      role: "user",
      parts: [{ type: "text", text }],
      createdAt: Date.now(),
    };
    const assistantMsg: AppMessage = {
      id: newId(),
      role: "assistant",
      parts: [],
      createdAt: Date.now(),
    };

    set((s) => ({
      messages: [...s.messages, userMsg, assistantMsg],
      isRunning: true,
    }));

    const payload = {
      messages: [...get().messages]
        .filter((m) => m.id !== assistantMsg.id)
        .map((m) => ({
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
      const res = await fetch(CHAT_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
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
      updateAssistant((m) => {
        m.parts.push({
          type: "text",
          text: `\n\n_⚠ ${(err as Error).message}_`,
        });
      });
    } finally {
      set({ isRunning: false });
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
    case "done":
      break;
  }
}
