"use client";

import { useEffect, useRef, useState } from "react";
import {
  ChevronDown,
  Folder,
  FileText,
  FilePen,
  Eye,
  Highlighter,
  Sparkles,
  Loader2,
  CheckCircle2,
  AlertCircle,
} from "lucide-react";
import { cn } from "@/lib/cn";
import { useChatStore } from "@/lib/chat-store";
import type { ToolCallPart } from "@/lib/types";

type IconComponent = React.ComponentType<{
  className?: string;
  strokeWidth?: number | string;
}>;

const TOOL_META: Record<
  string,
  { icon: IconComponent; label: string }
> = {
  list_tree: { icon: Folder, label: "browsing files" },
  create_folder: { icon: Folder, label: "creating folder" },
  read_file: { icon: FileText, label: "reading" },
  write_file: { icon: FilePen, label: "writing" },
  replace_in_file: { icon: FilePen, label: "patching" },
  replace_file_lines: { icon: FilePen, label: "patching lines" },
  delete_file: { icon: FilePen, label: "deleting" },
  display_file: { icon: Eye, label: "showing" },
  highlight: { icon: Highlighter, label: "highlighting" },
  snippet: { icon: Sparkles, label: "drafting" },
};

function summarize(part: ToolCallPart): string {
  const args = part.args ?? {};
  switch (part.toolName) {
    case "list_tree":
      return (args.path as string) || "/";
    case "create_folder":
      return (args.path as string) || "…";
    case "read_file":
    case "display_file":
      return (args.path as string) || "…";
    case "write_file": {
      const lines = String(args.content ?? "").split("\n").length;
      return `${args.path ?? "…"} · ${lines} line${lines === 1 ? "" : "s"}`;
    }
    case "replace_in_file":
      return `${args.path ?? "…"} · exact text`;
    case "replace_file_lines":
      return `${args.path ?? "…"} · L${args.start_line}–${args.end_line}`;
    case "delete_file":
      return `${args.path ?? "…"}`;
    case "highlight":
      return `${args.path ?? "…"} · L${args.start_line}–${args.end_line}`;
    case "snippet":
      return `${args.format ?? "markdown"}`;
    default:
      return "";
  }
}

function StatusIcon({ status }: { status: ToolCallPart["status"] }) {
  if (status === "streaming" || status === "executing")
    return (
      <Loader2 className="size-3 animate-spin text-ember" strokeWidth={1.6} />
    );
  if (status === "error")
    return (
      <AlertCircle className="size-3 text-ember" strokeWidth={1.6} />
    );
  return (
    <CheckCircle2
      className="size-3 text-bone-muted"
      strokeWidth={1.6}
    />
  );
}

/**
 * Reveals `value` with a quick typewriter effect, but only when it arrives
 * *live* (undefined → text). A value already present on first render — e.g. a
 * persisted preview when a thread is reopened — is shown instantly, so old
 * cards don't re-type on every load.
 */
function useTypewriter(value: string | undefined): { shown: string; typing: boolean } {
  const [shown, setShown] = useState(value ?? "");
  const [typing, setTyping] = useState(false);
  const prev = useRef(value);

  useEffect(() => {
    const before = prev.current;
    prev.current = value;

    if (!value) {
      setShown("");
      setTyping(false);
      return;
    }
    if (before) {
      // Already had a preview (reload or update) — no animation.
      setShown(value);
      setTyping(false);
      return;
    }

    // undefined -> text: type it in.
    setTyping(true);
    setShown("");
    let i = 0;
    const step = Math.max(1, Math.ceil(value.length / 32));
    const id = setInterval(() => {
      i = Math.min(value.length, i + step);
      setShown(value.slice(0, i));
      if (i >= value.length) {
        clearInterval(id);
        setTyping(false);
      }
    }, 18);
    return () => clearInterval(id);
  }, [value]);

  return { shown, typing };
}

export function ToolCallCard({ part }: { part: ToolCallPart }) {
  const [open, setOpen] = useState(false);
  const meta = TOOL_META[part.toolName] ?? {
    icon: Sparkles,
    label: part.toolName,
  };
  const Icon = meta.icon;
  const summary = summarize(part);
  // The LLM-generated narration lives on the store part (assistant-ui doesn't
  // forward custom fields through its tool-call props), so read it by id.
  const storePreview = useChatStore((s) => {
    for (const m of s.messages) {
      for (const p of m.parts) {
        if (p.type === "tool-call" && p.toolCallId === part.toolCallId) {
          return p.preview;
        }
      }
    }
    return undefined;
  });
  const preview = part.preview ?? storePreview;
  const { shown, typing } = useTypewriter(preview);
  const mainText = preview ? shown : summary || part.toolName;
  const isOpenable = !!part.args || !!part.result;

  return (
    <div
      className="tool-card my-2 rounded border border-rule bg-ground-2/40"
      data-status={part.status}
    >
      <button
        type="button"
        onClick={() => isOpenable && setOpen((o) => !o)}
        className={cn(
          "flex w-full items-center gap-2.5 px-3 py-2 text-left",
          isOpenable && "cursor-pointer hover:bg-ground-2"
        )}
      >
        <Icon
          className={cn(
            "size-3.5 shrink-0 text-bone-dim",
            (part.status === "streaming" || part.status === "executing") &&
              "text-ember"
          )}
          strokeWidth={1.6}
        />
        <span className="smallcaps text-bone-muted">{meta.label}</span>
        <span
          className={cn(
            "truncate text-xs",
            preview ? "italic text-bone-dim" : "font-mono",
            part.status === "streaming" && !preview
              ? "shimmer-text"
              : "text-bone-dim"
          )}
        >
          {mainText}
          {typing && (
            <span
              className="ml-px inline-block h-3 w-px translate-y-[2px] bg-ember ember-pulse"
              aria-hidden
            />
          )}
        </span>
        <span className="flex-1" />
        <StatusIcon status={part.status} />
        {isOpenable && (
          <ChevronDown
            className={cn(
              "size-3 text-bone-muted transition-transform",
              open && "rotate-180"
            )}
            strokeWidth={1.6}
          />
        )}
      </button>

      {open && (
        <div className="border-t border-rule px-3 py-2 font-mono text-[11px]">
          {part.args && (
            <details open className="mb-1.5">
              <summary className="cursor-pointer smallcaps">arguments</summary>
              <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap text-bone-dim">
                {JSON.stringify(part.args, null, 2)}
              </pre>
            </details>
          )}
          {part.result !== undefined && (
            <details>
              <summary className="cursor-pointer smallcaps">result</summary>
              <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap text-bone-dim">
                {typeof part.result === "string"
                  ? part.result
                  : JSON.stringify(part.result, null, 2)}
              </pre>
            </details>
          )}
        </div>
      )}
    </div>
  );
}
