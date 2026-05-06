"use client";

import { useState } from "react";
import {
  ThreadPrimitive,
  MessagePrimitive,
  ComposerPrimitive,
  type TextMessagePartComponent,
  type ToolCallMessagePartComponent,
} from "@assistant-ui/react";
import { ArrowUp, ChevronDown, Square, Sparkles } from "lucide-react";
import { Markdown } from "./markdown";
import { ToolCallCard } from "./tool-call";
import { useChatStore } from "@/lib/chat-store";
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
        <div className="flex-1 overflow-x-auto text-bone">
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
        <div className="flex-1 min-w-0 overflow-x-auto text-bone">
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
            "composer-input max-h-40 flex-1 resize-none rounded-none bg-transparent py-1.5 text-sm text-bone placeholder:text-bone-muted focus:outline-none focus-visible:outline-none"
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
  const systemPrompts = useChatStore((s) => s.systemPrompts);
  const activeSystemPromptId = useChatStore((s) => s.activeSystemPromptId);
  const selectSystemPrompt = useChatStore((s) => s.selectSystemPrompt);
  const createSystemPrompt = useChatStore((s) => s.createSystemPrompt);
  const updateSystemPrompt = useChatStore((s) => s.updateSystemPrompt);
  const isRunning = useChatStore((s) => s.isRunning);
  const activeSystemPrompt =
    systemPrompts.find((prompt) => prompt.id === activeSystemPromptId) ?? null;
  const [promptEditorOpen, setPromptEditorOpen] = useState(false);
  const [promptEditing, setPromptEditing] = useState(false);
  const [promptCreating, setPromptCreating] = useState(false);
  const [draftPromptName, setDraftPromptName] = useState("");
  const [draftPromptContent, setDraftPromptContent] = useState("");

  const openPromptEditor = () => {
    if (!activeSystemPrompt) return;
    setDraftPromptName(activeSystemPrompt.name);
    setDraftPromptContent(activeSystemPrompt.content);
    setPromptEditorOpen(true);
    setPromptEditing(false);
    setPromptCreating(false);
  };

  const startNewPrompt = () => {
    setDraftPromptName("New prompt");
    setDraftPromptContent(activeSystemPrompt?.content ?? "");
    setPromptEditorOpen(true);
    setPromptEditing(true);
    setPromptCreating(true);
  };

  const savePrompt = async () => {
    if (!draftPromptName.trim() || !draftPromptContent.trim()) {
      return;
    }
    if (promptCreating) {
      await createSystemPrompt(draftPromptName.trim(), draftPromptContent);
      setPromptCreating(false);
      setPromptEditing(false);
      return;
    }
    if (!activeSystemPrompt) return;
    await updateSystemPrompt(
      activeSystemPrompt.id,
      draftPromptName.trim(),
      draftPromptContent
    );
    setPromptEditing(false);
  };

  return (
    <ThreadPrimitive.Root className="flex h-full min-h-0 flex-col bg-ground">
      <div className="shrink-0 border-b border-rule">
        <header className="flex items-center gap-3 px-6 py-3.5">
          <span className="size-1.5 rounded-full bg-ember" />
          <span className="font-display text-base italic text-bone">
            studio
          </span>
          <span className="flex-1" />
          <button
            type="button"
            disabled={systemPrompts.length === 0 || isRunning}
            onClick={openPromptEditor}
            className={cn(
              "group flex max-w-[17rem] shrink-0 items-center gap-2 rounded-full border px-3 py-1.5 text-left transition-colors disabled:opacity-40",
              promptEditorOpen
                ? "border-ember/50 bg-ember-soft text-bone"
                : "border-rule bg-ground-2/45 text-bone-dim hover:border-rule-strong hover:bg-ground-2 hover:text-bone"
            )}
          >
            <span className="size-1.5 shrink-0 rounded-full bg-ember" />
            <span className="smallcaps text-[9.5px]">prompt</span>
            <span className="min-w-0 flex-1 truncate font-mono text-[11px]">
              {activeSystemPrompt?.name ?? "loading"}
            </span>
            <ChevronDown
              className={cn(
                "size-3 shrink-0 transition-transform",
                promptEditorOpen && "rotate-180"
              )}
              strokeWidth={1.6}
            />
          </button>
        </header>

        {promptEditorOpen && activeSystemPrompt && (
          <div className="border-t border-rule bg-ground-2/30 px-6 py-4">
            <div className="mx-auto grid max-w-[44rem] gap-4 md:grid-cols-[13rem_minmax(0,1fr)]">
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="smallcaps">prompt presets</span>
                  <button
                    type="button"
                    onClick={startNewPrompt}
                    className="rounded px-1.5 py-0.5 font-mono text-[10.5px] text-bone-muted hover:bg-ground-2 hover:text-bone"
                  >
                    new
                  </button>
                </div>
                <div className="space-y-1 rounded border border-rule bg-ground/45 p-1">
                  {systemPrompts.map((prompt) => {
                    const active = prompt.id === activeSystemPromptId;
                    return (
                      <button
                        key={prompt.id}
                        type="button"
                        onClick={() => {
                          selectSystemPrompt(prompt.id).catch(() => undefined);
                          setDraftPromptName(prompt.name);
                          setDraftPromptContent(prompt.content);
                          setPromptEditing(false);
                          setPromptCreating(false);
                        }}
                        className={cn(
                          "flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-[11.5px] transition-colors",
                          active
                            ? "bg-ember-soft text-bone"
                            : "text-bone-dim hover:bg-ground-2 hover:text-bone"
                        )}
                      >
                        <span
                          className={cn(
                            "size-1.5 shrink-0 rounded-full",
                            active ? "bg-ember" : "bg-bone-muted"
                          )}
                        />
                        <span className="min-w-0 flex-1 truncate">
                          {prompt.name}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="min-w-0 rounded border border-rule bg-ground/55">
                <div className="flex items-center gap-2 border-b border-rule px-3 py-2">
                  <div className="min-w-0 flex-1">
                    <span className="smallcaps block">
                      {promptCreating ? "new system prompt" : "active system prompt"}
                    </span>
                    <span className="block truncate font-display text-lg italic text-bone">
                      {promptCreating ? draftPromptName : activeSystemPrompt.name}
                    </span>
                  </div>
                  {!promptEditing ? (
                    <button
                      type="button"
                      onClick={() => setPromptEditing(true)}
                      className="rounded border border-rule px-2 py-1 font-mono text-[11px] text-bone-muted hover:bg-ground-2 hover:text-bone"
                    >
                      edit
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={() => savePrompt().catch(() => undefined)}
                      className="rounded bg-ember px-2 py-1 font-mono text-[11px] text-ground hover:opacity-90"
                    >
                      save
                    </button>
                  )}
                </div>

                <div className="space-y-2 p-3">
                  {promptEditing ? (
                    <>
                      <input
                        value={draftPromptName}
                        onChange={(e) => setDraftPromptName(e.target.value)}
                        className="w-full rounded border border-rule bg-ground-2 px-2 py-1.5 text-xs text-bone outline-none focus:border-ember/60"
                      />
                      <textarea
                        value={draftPromptContent}
                        onChange={(e) => setDraftPromptContent(e.target.value)}
                        rows={10}
                        className="w-full resize-y rounded border border-rule bg-ground-2 px-2 py-2 font-mono text-[11px] leading-relaxed text-bone outline-none focus:border-ember/60"
                      />
                    </>
                  ) : (
                    <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded bg-ground-2/70 p-3 font-mono text-[11px] leading-relaxed text-bone-dim">
                      {activeSystemPrompt.content}
                    </pre>
                  )}
                </div>

                <div className="flex items-center justify-between border-t border-rule px-3 py-2">
                  <span className="font-mono text-[10px] text-bone-muted">
                    per-chat prompt
                  </span>
                  <div className="flex gap-2">
                    {promptEditing && (
                      <button
                        type="button"
                        onClick={() => {
                          setPromptEditing(false);
                          setPromptCreating(false);
                          setDraftPromptName(activeSystemPrompt.name);
                          setDraftPromptContent(activeSystemPrompt.content);
                        }}
                        className="rounded px-2 py-1 text-[11px] text-bone-muted hover:bg-ground-2 hover:text-bone"
                      >
                        cancel
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => setPromptEditorOpen(false)}
                      className="rounded px-2 py-1 text-[11px] text-bone-muted hover:bg-ground-2 hover:text-bone"
                    >
                      close
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

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
