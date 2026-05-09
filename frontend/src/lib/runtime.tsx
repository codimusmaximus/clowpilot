"use client";

import { useEffect, useMemo } from "react";
import {
  AssistantRuntimeProvider,
  ExportedMessageRepository,
  useExternalStoreRuntime,
} from "@assistant-ui/react";
import { useChatStore } from "./chat-store";
import type { AppMessage } from "./types";

function toThreadMessageLike(m: AppMessage) {
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
  const headId = useChatStore((s) => s.headId);
  const isRunning = useChatStore((s) => s.isRunning);
  const load = useChatStore((s) => s.load);
  const send = useChatStore((s) => s.send);
  const editMessage = useChatStore((s) => s.editMessage);
  const setHeadId = useChatStore((s) => s.setHeadId);

  useEffect(() => {
    load().catch(() => undefined);
  }, [load]);

  const messageRepository = useMemo(
    () =>
      ExportedMessageRepository.fromBranchableArray(
        messages.map((m) => ({ message: toThreadMessageLike(m), parentId: m.parentId })),
        { headId: headId ?? undefined },
      ),
    [messages, headId],
  );

  const extractText = (msg: { content: unknown }) =>
    (msg.content as Array<{ type: string; text?: string }>)
      .filter((p) => p.type === "text" && p.text)
      .map((p) => p.text!)
      .join("");

  // convertMessage is intentionally omitted: when messageRepository is used the runtime
  // calls setMessages with ThreadMessage[] (not AppMessage[]), so we can extract IDs directly.
  // Passing convertMessage causes updateMessages to call flatMap(getExternalStoreMessages)
  // which returns [] for repo-sourced messages, breaking branch navigation.
  const runtime = useExternalStoreRuntime({
    isRunning,
    messageRepository,
    setMessages: (msgs) => {
      const lastId = msgs.length > 0 ? (msgs[msgs.length - 1] as { id?: string })?.id ?? null : null;
      if (lastId) setHeadId(lastId);
    },
    onNew: async (msg) => {
      await send(extractText(msg), msg.parentId);
    },
    onEdit: async (msg) => {
      await editMessage(msg.sourceId, extractText(msg), msg.parentId);
    },
  });

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      {children}
    </AssistantRuntimeProvider>
  );
}
