"use client";

import { useMemo } from "react";
import {
  ThreadPrimitive,
  MessagePrimitive,
  ComposerPrimitive,
  ActionBarPrimitive,
  BranchPickerPrimitive,
  unstable_useSlashCommandAdapter,
  type TextMessagePartComponent,
  type ToolCallMessagePartComponent,
  type Unstable_SlashCommand,
} from "@assistant-ui/react";
import {
  ArrowUp,
  ChevronLeft,
  ChevronRight,
  Pencil,
  PanelRight,
  Square,
  Sparkles,
} from "lucide-react";
import { Markdown } from "./markdown";
import { ToolCallCard } from "./tool-call";
import { useChatStore } from "@/lib/chat-store";
import { useUIStore } from "@/lib/ui-store";
import { createPluginContextCommands } from "@/lib/plugin-context";
import type { PluginStatus, ToolCallStatus } from "@/lib/types";
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

function BranchNav() {
  return (
    <BranchPickerPrimitive.Root
      hideWhenSingleBranch
      className="mt-2 flex items-center gap-0.5 text-bone-muted"
    >
      <BranchPickerPrimitive.Previous asChild>
        <button
          type="button"
          className="rounded p-0.5 hover:bg-ground-2 hover:text-bone disabled:opacity-30"
        >
          <ChevronLeft className="size-3" strokeWidth={1.6} />
        </button>
      </BranchPickerPrimitive.Previous>
      <span className="font-mono text-[10px] tabular-nums">
        <BranchPickerPrimitive.Number /> / <BranchPickerPrimitive.Count />
      </span>
      <BranchPickerPrimitive.Next asChild>
        <button
          type="button"
          className="rounded p-0.5 hover:bg-ground-2 hover:text-bone disabled:opacity-30"
        >
          <ChevronRight className="size-3" strokeWidth={1.6} />
        </button>
      </BranchPickerPrimitive.Next>
    </BranchPickerPrimitive.Root>
  );
}

function UserMessage() {
  return (
    <MessagePrimitive.Root asChild>
      <div className="group mx-auto flex w-full max-w-[44rem] items-start gap-3 px-6 py-4">
        <div className="mt-1 shrink-0">
          <span className="smallcaps">you</span>
        </div>
        <div className="flex-1 overflow-x-auto text-bone">
          <MessagePrimitive.Parts components={partsConfig} />
          <BranchNav />
        </div>
        <ActionBarPrimitive.Root
          hideWhenRunning
          autohide="always"
          className="mt-0.5 flex shrink-0 gap-1 opacity-0 transition-opacity group-hover:opacity-100 data-[floating]:opacity-100"
        >
          <ActionBarPrimitive.Edit asChild>
            <button
              type="button"
              aria-label="edit message"
              className="rounded p-1 text-bone-muted hover:bg-ground-2 hover:text-bone"
            >
              <Pencil className="size-3" strokeWidth={1.6} />
            </button>
          </ActionBarPrimitive.Edit>
        </ActionBarPrimitive.Root>
      </div>
    </MessagePrimitive.Root>
  );
}

function EditComposer() {
  return (
    <div className="mx-auto flex w-full max-w-[44rem] items-start gap-3 px-6 py-4">
      <div className="mt-1 shrink-0">
        <span className="smallcaps">you</span>
      </div>
      <div className="flex-1 min-w-0 flex flex-col gap-2 rounded border border-ember/50 bg-ground-2/40 px-3 py-2 focus-within:border-ember/70">
        <ComposerPrimitive.Input
          rows={1}
          className="max-h-40 resize-none bg-transparent py-1 text-sm text-bone placeholder:text-bone-muted focus:outline-none"
        />
        <div className="flex justify-end gap-2">
          <ComposerPrimitive.Cancel asChild>
            <button
              type="button"
              className="rounded px-3 py-1 text-[11px] text-bone-muted hover:bg-ground-2 hover:text-bone"
            >
              cancel
            </button>
          </ComposerPrimitive.Cancel>
          <ComposerPrimitive.Send asChild>
            <button
              type="submit"
              className="rounded bg-ember px-3 py-1 text-[11px] text-ground hover:opacity-90"
            >
              save
            </button>
          </ComposerPrimitive.Send>
        </div>
      </div>
    </div>
  );
}

function AssistantMessage() {
  return (
    <MessagePrimitive.Root asChild>
      <div className="group mx-auto flex w-full max-w-[44rem] gap-3 px-6 py-4">
        <div className="mt-1 shrink-0">
          <span className="smallcaps text-ember">studio</span>
        </div>
        <div className="flex-1 min-w-0 overflow-x-auto text-bone">
          <MessagePrimitive.Parts components={partsConfig} />
          <BranchNav />
        </div>
      </div>
    </MessagePrimitive.Root>
  );
}

const examples = [
  "Read the welcome note and walk me through it.",
  "Make a markdown TL;DR of customers.csv as a table.",
  "Create a Python script that sums MRR from the CSV — show it and explain.",
  "Highlight the comment-pinning rule in welcome.md.",
];

function EmptyState() {
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
              <ThreadPrimitive.Suggestion prompt={ex} method="replace" autoSend asChild>
                <button className="group flex w-full items-center gap-3 py-2.5 text-left hover:text-bone">
                  <Sparkles className="size-3 text-bone-muted transition-colors group-hover:text-ember" strokeWidth={1.6} />
                  <span className="flex-1 text-sm text-bone-dim transition-colors group-hover:text-bone">{ex}</span>
                </button>
              </ThreadPrimitive.Suggestion>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function SlashCommandItems() {
  return (
    <ComposerPrimitive.Unstable_TriggerPopoverItems>
      {(items) => (
        <div className="max-h-72 min-w-72 overflow-auto rounded border border-rule-strong bg-ground-2 p-1 shadow-2xl">
          {items.map((item, index) => (
            <ComposerPrimitive.Unstable_TriggerPopoverItem
              key={item.id}
              item={item}
              index={index}
              className="flex cursor-pointer flex-col gap-0.5 rounded px-2.5 py-2 text-left data-[highlighted]:bg-ember-soft"
            >
              <span className="font-mono text-[11px] text-bone">{item.label}</span>
              {item.description && (
                <span className="text-[10.5px] text-bone-muted">{item.description}</span>
              )}
            </ComposerPrimitive.Unstable_TriggerPopoverItem>
          ))}
        </div>
      )}
    </ComposerPrimitive.Unstable_TriggerPopoverItems>
  );
}

function Composer({ plugins }: { plugins: PluginStatus[] }) {
  const isRunning = useChatStore((s) => s.isRunning);
  const slashCommands = useMemo<Unstable_SlashCommand[]>(() => {
    return createPluginContextCommands(plugins.filter((p) => p.enabled)).map(
      (command) => ({ ...command, execute: () => undefined })
    );
  }, [plugins]);

  const slash = unstable_useSlashCommandAdapter({ commands: slashCommands });

  return (
    <div className="border-t border-rule bg-ground/95 px-6 py-4 backdrop-blur">
      <ComposerPrimitive.Unstable_TriggerPopoverRoot>
        <ComposerPrimitive.Root className="relative mx-auto flex w-full max-w-[44rem] items-end gap-2 rounded border border-rule-strong bg-ground-2/40 px-3 py-2 transition-colors focus-within:border-ember/60">
          <ComposerPrimitive.Input
            autoFocus
            rows={1}
            placeholder="Ask the studio… type / for plugins and tools"
            data-gramm="false"
            data-gramm_editor="false"
            data-enable-grammarly="false"
            className={cn(
              "composer-input max-h-40 flex-1 resize-none rounded-none bg-transparent py-1.5 text-sm text-bone placeholder:text-bone-muted focus:outline-none focus-visible:outline-none"
            )}
          />
          {isRunning ? (
            <button
              type="button"
              aria-label="stop"
              onClick={() => useChatStore.getState().stopGeneration()}
              className="flex size-7 items-center justify-center rounded border border-rule text-bone-dim hover:bg-ground-2 hover:text-bone"
            >
              <Square className="size-3" strokeWidth={1.6} fill="currentColor" />
            </button>
          ) : (
            <ComposerPrimitive.Send asChild>
              <button
                type="submit"
                aria-label="send"
                className="flex size-7 items-center justify-center rounded bg-ember text-ground transition-opacity hover:opacity-90 disabled:opacity-30"
              >
                <ArrowUp className="size-3.5" strokeWidth={2} />
              </button>
            </ComposerPrimitive.Send>
          )}

          <ComposerPrimitive.Unstable_TriggerPopover
            char="/"
            adapter={slash.adapter}
            className="absolute bottom-full left-0 z-50 mb-2"
          >
            <ComposerPrimitive.Unstable_TriggerPopover.Action {...slash.action} />
            <SlashCommandItems />
          </ComposerPrimitive.Unstable_TriggerPopover>
        </ComposerPrimitive.Root>
      </ComposerPrimitive.Unstable_TriggerPopoverRoot>
      <p className="mx-auto mt-2 max-w-[44rem] text-[10.5px] text-bone-muted">
        <span className="font-mono">⌘↵</span> to send · the assistant uses
        tools to act on the workspace · <span className="font-mono">/</span>{" "}
        adds plugin/tool context
      </p>
    </div>
  );
}

export function Chat() {
  const isRunning = useChatStore((s) => s.isRunning);
  const plugins = useChatStore((s) => s.plugins);
  const rightOpen = useUIStore((s) => s.rightOpen);
  const toggleRight = useUIStore((s) => s.toggleRight);

  return (
    <ThreadPrimitive.Root className="flex h-full w-full min-h-0 flex-col bg-ground">
      <header className="shrink-0 border-b border-rule flex items-center gap-3 px-6 py-3.5">
        <span className="size-1.5 rounded-full bg-ember" />
        <span className="font-display text-base italic text-bone">studio</span>
        <span className="flex-1" />
        <button
          type="button"
          onClick={toggleRight}
          title={rightOpen ? "close workspace" : "open workspace"}
          aria-label={rightOpen ? "close workspace" : "open workspace"}
          className={cn(
            "rounded p-1.5 transition-colors",
            rightOpen
              ? "text-bone-muted hover:bg-ground-2 hover:text-bone"
              : "text-ember hover:bg-ember-soft"
          )}
        >
          <PanelRight className="size-4" strokeWidth={1.6} />
        </button>
      </header>

      <ThreadPrimitive.Viewport autoScroll className="flex-1 min-h-0 overflow-y-auto">
        <ThreadPrimitive.Empty>
          <EmptyState />
        </ThreadPrimitive.Empty>
        <ThreadPrimitive.Messages
          components={{ UserMessage, AssistantMessage, EditComposer }}
        />
        <div className="h-6" />
      </ThreadPrimitive.Viewport>

      <Composer plugins={plugins} />
    </ThreadPrimitive.Root>
  );
}
