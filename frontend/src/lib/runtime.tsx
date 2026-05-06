"use client";

import {
  AssistantRuntimeProvider,
  useExternalStoreRuntime,
} from "@assistant-ui/react";
import { useChatStore } from "./chat-store";
import type { AppMessage } from "./types";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function convertMessage(m: AppMessage): any {
  return {
    id: m.id,
    role: m.role,
    content: m.parts.map((p) => {
      if (p.type === "text") return { type: "text" as const, text: p.text };
      return {
        type: "tool-call" as const,
        toolCallId: p.toolCallId,
        toolName: p.toolName,
        args: p.args ?? {},
        argsText: p.argsText ?? "",
        result: p.result,
        isError: p.status === "error",
      };
    }),
    createdAt: new Date(m.createdAt),
  };
}

export function CopilotRuntimeProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const messages = useChatStore((s) => s.messages);
  const isRunning = useChatStore((s) => s.isRunning);
  const send = useChatStore((s) => s.send);

  const runtime = useExternalStoreRuntime<AppMessage>({
    isRunning,
    messages,
    convertMessage,
    onNew: async (msg) => {
      const text = (msg.content as Array<{ type: string; text?: string }>)
        .filter((p) => p.type === "text" && p.text)
        .map((p) => p.text!)
        .join("");
      await send(text);
    },
  });

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      {children}
    </AssistantRuntimeProvider>
  );
}
