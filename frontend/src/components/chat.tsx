"use client";

import {
  ThreadPrimitive,
  MessagePrimitive,
  ComposerPrimitive,
  type TextMessagePartComponent,
  type ToolCallMessagePartComponent,
} from "@assistant-ui/react";
import { ArrowUp, Square, Sparkles } from "lucide-react";
import { Markdown } from "./markdown";
import { ToolCallCard } from "./tool-call";
import type { ToolCallStatus } from "@/lib/types";
import { cn } from "@/lib/cn";

const TextPart: TextMessagePartComponent = ({ text, status }) => {
  if (text === "" && status?.type === "running") {
    return (
      <span
        className="inline-block size-1.5 translate-y-[-1px] rounded-full bg-ember ember-pulse"
        aria-label="thinking"
      />
    );
  }
  return <Markdown>{text}</Markdown>;
};

const ToolFallback: ToolCallMessagePartComponent = ({
  toolCallId,
  toolName,
  args,
  argsText,
  result,
  isError,
  status,
}) => {
  let myStatus: ToolCallStatus;
  if (isError) myStatus = "error";
  else if (result !== undefined) myStatus = "done";
  else if (status?.type === "running") {
    const hasArgs = args && Object.keys(args as object).length > 0;
    myStatus = hasArgs ? "executing" : "streaming";
  } else myStatus = "ready";

  return (
    <ToolCallCard
      part={{
        type: "tool-call",
        toolCallId,
        toolName,
        args: (args ?? undefined) as Record<string, unknown> | undefined,
        argsText,
        result,
        status: myStatus,
      }}
    />
  );
};

const partsConfig = {
  Text: TextPart,
  tools: { Fallback: ToolFallback },
} as const;

function UserMessage() {
  return (
    <MessagePrimitive.Root asChild>
      <div className="group mx-auto flex w-full max-w-[44rem] gap-3 px-6 py-4">
        <div className="mt-1 shrink-0">
          <span className="smallcaps">you</span>
        </div>
        <div className="flex-1 text-bone">
          <MessagePrimitive.Parts components={partsConfig} />
        </div>
      </div>
    </MessagePrimitive.Root>
  );
}

function AssistantMessage() {
  return (
    <MessagePrimitive.Root asChild>
      <div className="group mx-auto flex w-full max-w-[44rem] gap-3 px-6 py-4">
        <div className="mt-1 shrink-0">
          <span className="smallcaps text-ember">studio</span>
        </div>
        <div className="flex-1 min-w-0 text-bone">
          <MessagePrimitive.Parts components={partsConfig} />
        </div>
      </div>
    </MessagePrimitive.Root>
  );
}

function EmptyState() {
  const examples = [
    "Read the welcome note and walk me through it.",
    "Make a markdown TL;DR of customers.csv as a table.",
    "Create a Python script that sums MRR from the CSV — show it and explain.",
    "Highlight the comment-pinning rule in welcome.md.",
  ];
  return (
    <div className="mx-auto flex w-full max-w-[44rem] flex-col gap-6 px-6 pt-12">
      <div className="space-y-1">
        <span className="smallcaps">studio</span>
        <h1 className="font-display text-[2.6rem] leading-[1.05] tracking-[-0.015em]">
          A copilot that <em className="not-italic font-display italic">narrates</em> in chat
          and <em className="not-italic font-display italic">shows</em> in the workspace.
        </h1>
        <p className="pt-3 text-sm text-bone-dim">
          The assistant has access to the file sandbox on the left. It can read,
          create, display, and annotate files — and render ad-hoc snippets in
          the workspace pane on the right.
        </p>
      </div>

      <div className="space-y-1.5">
        <span className="smallcaps">try</span>
        <ul className="divide-y divide-rule border-y border-rule">
          {examples.map((ex) => (
            <li key={ex}>
              <ThreadPrimitive.Suggestion
                prompt={ex}
                method="replace"
                autoSend
                asChild
              >
                <button className="group flex w-full items-center gap-3 py-2.5 text-left hover:text-bone">
                  <Sparkles
                    className="size-3 text-bone-muted transition-colors group-hover:text-ember"
                    strokeWidth={1.6}
                  />
                  <span className="flex-1 text-sm text-bone-dim transition-colors group-hover:text-bone">
                    {ex}
                  </span>
                </button>
              </ThreadPrimitive.Suggestion>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function Composer() {
  return (
    <div className="border-t border-rule bg-ground/95 px-6 py-4 backdrop-blur">
      <ComposerPrimitive.Root className="mx-auto flex w-full max-w-[44rem] items-end gap-2 rounded border border-rule-strong bg-ground-2/40 px-3 py-2 transition-colors focus-within:border-ember/60">
        <ComposerPrimitive.Input
          autoFocus
          rows={1}
          placeholder="Ask the studio…"
          className={cn(
            "max-h-40 flex-1 resize-none bg-transparent py-1.5 text-sm text-bone placeholder:text-bone-muted focus:outline-none"
          )}
        />
        <ThreadPrimitive.If running>
          <ComposerPrimitive.Cancel asChild>
            <button
              type="button"
              aria-label="stop"
              className="flex size-7 items-center justify-center rounded border border-rule text-bone-dim hover:bg-ground-2"
            >
              <Square className="size-3" strokeWidth={1.6} fill="currentColor" />
            </button>
          </ComposerPrimitive.Cancel>
        </ThreadPrimitive.If>
        <ThreadPrimitive.If running={false}>
          <ComposerPrimitive.Send asChild>
            <button
              type="submit"
              aria-label="send"
              className="flex size-7 items-center justify-center rounded bg-ember text-ground transition-opacity hover:opacity-90 disabled:opacity-30"
            >
              <ArrowUp className="size-3.5" strokeWidth={2} />
            </button>
          </ComposerPrimitive.Send>
        </ThreadPrimitive.If>
      </ComposerPrimitive.Root>
      <p className="mx-auto mt-2 max-w-[44rem] text-[10.5px] text-bone-muted">
        <span className="font-mono">⌘↵</span> to send · the assistant uses
        tools to act on the workspace
      </p>
    </div>
  );
}

export function Chat() {
  return (
    <ThreadPrimitive.Root className="flex h-full min-h-0 flex-col bg-ground">
      <header className="flex shrink-0 items-center gap-3 border-b border-rule px-6 py-3.5">
        <span className="size-1.5 rounded-full bg-ember" />
        <span className="font-display text-base italic text-bone">
          studio
        </span>
        <span className="smallcaps">copilot · workspace agent</span>
      </header>

      <ThreadPrimitive.Viewport
        autoScroll
        className="flex-1 min-h-0 overflow-y-auto"
      >
        <ThreadPrimitive.Empty>
          <EmptyState />
        </ThreadPrimitive.Empty>

        <ThreadPrimitive.Messages
          components={{
            UserMessage,
            AssistantMessage,
            EditComposer: () => null,
          }}
        />

        <div className="h-6" />
      </ThreadPrimitive.Viewport>

      <Composer />
    </ThreadPrimitive.Root>
  );
}
