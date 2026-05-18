"use client";

import { useEffect, useMemo } from "react";
import {
  AssistantRuntimeProvider,
  ExportedMessageRepository,
  SimpleTextAttachmentAdapter,
  useExternalStoreRuntime,
  type PendingAttachment,
  type ThreadMessage,
} from "@assistant-ui/react";
import { uploadAttachment, uploadedAttachmentToRecord } from "./api";
import { useChatStore } from "./chat-store";
import type { AppMessage, AttachmentRecord } from "./types";

type ReadonlyJsonValue =
  | null
  | string
  | number
  | boolean
  | readonly ReadonlyJsonValue[]
  | { readonly [key: string]: ReadonlyJsonValue };

type ReadonlyJsonObject = { readonly [key: string]: ReadonlyJsonValue };

const asReadonlyJsonObject = (
  value: Record<string, unknown> | undefined,
): ReadonlyJsonObject => (value ?? {}) as ReadonlyJsonObject;

function normalizeAttachments(
  attachments: AppMessage["attachments"],
): AttachmentRecord[] | undefined {
  if (!attachments || attachments.length === 0) return undefined;
  return attachments.map((attachment) => ({
    ...attachment,
    type: attachment.type ?? "document",
    contentType: attachment.contentType ?? attachment.content[0]?.mimeType ?? "application/octet-stream",
    content: attachment.content ?? [],
    status: attachment.status ?? { type: "complete" },
  }));
}

function toThreadMessageLike(m: AppMessage) {
  const textContent = m.parts
    .filter((p): p is Extract<AppMessage["parts"][number], { type: "text" }> => p.type === "text")
    .map((p) => ({ type: "text" as const, text: p.text }));

  const toolContent = m.parts
    .filter((p): p is Extract<AppMessage["parts"][number], { type: "tool-call" }> => p.type === "tool-call")
    .map((p) => ({
      type: "tool-call" as const,
      toolCallId: p.toolCallId,
      toolName: p.toolName,
      args: asReadonlyJsonObject(p.args),
      argsText: p.argsText ?? "",
      result: p.result,
      isError: p.status === "error",
    }));

  return {
    id: m.id,
    role: m.role,
    content: [...textContent, ...toolContent],
    attachments: normalizeAttachments(m.attachments),
    createdAt: new Date(m.createdAt),
  };
}

class WorkspaceAttachmentAdapter extends SimpleTextAttachmentAdapter {
  override accept = "image/*,text/*,application/pdf,.md,.txt,.csv,.json,.py,.ts,.tsx,.js,.jsx,.html,.css,.sql,.yaml,.yml";

  override async send(attachment: PendingAttachment): Promise<AttachmentRecord> {
    const conversationId = useChatStore.getState().activeConversationId;
    const uploaded = await uploadAttachment(attachment.file, conversationId);
    return uploadedAttachmentToRecord(uploaded);
  }
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

  const extractAttachments = (msg: { attachments?: unknown }) =>
    Array.isArray(msg.attachments)
      ? (msg.attachments as AttachmentRecord[])
      : undefined;

  // convertMessage is intentionally omitted: when messageRepository is used the runtime
  // calls setMessages with ThreadMessage[] (not AppMessage[]), so we can extract IDs directly.
  // Passing convertMessage causes updateMessages to call flatMap(getExternalStoreMessages)
  // which returns [] for repo-sourced messages, breaking branch navigation.
  const runtime = useExternalStoreRuntime<ThreadMessage>({
    isRunning,
    adapters: { attachments: new WorkspaceAttachmentAdapter() },
    messageRepository,
    setMessages: (msgs) => {
      const lastId = msgs.length > 0 ? (msgs[msgs.length - 1] as { id?: string })?.id ?? null : null;
      if (lastId) setHeadId(lastId);
    },
    onNew: async (msg) => {
      await send(extractText(msg), msg.parentId, extractAttachments(msg));
    },
    onEdit: async (msg) => {
      await editMessage(msg.sourceId, extractText(msg), msg.parentId, extractAttachments(msg));
    },
  });

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      {children}
    </AssistantRuntimeProvider>
  );
}
