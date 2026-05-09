"use client";

import { useEffect, useState } from "react";
import { X, Plus } from "lucide-react";
import { cn } from "@/lib/cn";
import { useChatStore } from "@/lib/chat-store";
import { useUIStore } from "@/lib/ui-store";

export function PromptModal() {
  const open = useUIStore((s) => s.promptModalOpen);
  const closePromptModal = useUIStore((s) => s.closePromptModal);

  const systemPrompts = useChatStore((s) => s.systemPrompts);
  const activeSystemPromptId = useChatStore((s) => s.activeSystemPromptId);
  const selectSystemPrompt = useChatStore((s) => s.selectSystemPrompt);
  const createSystemPrompt = useChatStore((s) => s.createSystemPrompt);
  const updateSystemPrompt = useChatStore((s) => s.updateSystemPrompt);

  const activePrompt = systemPrompts.find((p) => p.id === activeSystemPromptId) ?? null;

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [creating, setCreating] = useState(false);
  const [draftName, setDraftName] = useState("");
  const [draftContent, setDraftContent] = useState("");

  const selectedPrompt = systemPrompts.find((p) => p.id === selectedId) ?? activePrompt;

  useEffect(() => {
    if (open) {
      setSelectedId(activeSystemPromptId);
      setEditing(false);
      setCreating(false);
      setDraftName(activePrompt?.name ?? "");
      setDraftContent(activePrompt?.content ?? "");
    }
  }, [open, activeSystemPromptId, activePrompt]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") closePromptModal();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [closePromptModal]);

  if (!open) return null;

  const selectPrompt = (id: string) => {
    setSelectedId(id);
    setEditing(false);
    setCreating(false);
    const p = systemPrompts.find((x) => x.id === id);
    if (p) { setDraftName(p.name); setDraftContent(p.content); }
  };

  const startNew = () => {
    setSelectedId(null);
    setCreating(true);
    setEditing(true);
    setDraftName("New prompt");
    setDraftContent(selectedPrompt?.content ?? "");
  };

  const save = async () => {
    if (!draftName.trim() || !draftContent.trim()) return;
    if (creating) {
      await createSystemPrompt(draftName.trim(), draftContent).catch(() => undefined);
      setCreating(false);
      setEditing(false);
      return;
    }
    if (!selectedPrompt) return;
    await updateSystemPrompt(selectedPrompt.id, draftName.trim(), draftContent).catch(() => undefined);
    setEditing(false);
  };

  const activate = async () => {
    if (!selectedPrompt) return;
    await selectSystemPrompt(selectedPrompt.id).catch(() => undefined);
  };

  const isActive = selectedPrompt?.id === activeSystemPromptId;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={(e) => { if (e.target === e.currentTarget) closePromptModal(); }}
    >
      <div className="flex h-[600px] w-full max-w-2xl flex-col rounded border border-rule bg-ground shadow-2xl mx-4">
        {/* header */}
        <div className="flex shrink-0 items-center gap-3 border-b border-rule px-5 py-3.5">
          <span className="size-1.5 rounded-full bg-ember" />
          <span className="smallcaps">system prompts</span>
          <span className="flex-1" />
          <button
            type="button"
            aria-label="close"
            onClick={closePromptModal}
            className="rounded p-1 text-bone-muted hover:bg-ground-2 hover:text-bone"
          >
            <X className="size-4" strokeWidth={1.6} />
          </button>
        </div>

        {/* body */}
        <div className="flex min-h-0 flex-1">
          {/* prompt list */}
          <div className="flex w-52 shrink-0 flex-col border-r border-rule">
            <div className="flex shrink-0 items-center gap-2 px-3 py-2.5">
              <span className="smallcaps flex-1 text-[10px]">presets</span>
              <button
                type="button"
                onClick={startNew}
                className="rounded p-0.5 text-bone-muted hover:bg-ground-2 hover:text-bone"
                title="New prompt"
              >
                <Plus className="size-3" strokeWidth={1.6} />
              </button>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
              <div className="space-y-0.5 rounded border border-rule bg-ground/45 p-1">
                {systemPrompts.map((p) => {
                  const sel = p.id === (selectedId ?? activeSystemPromptId);
                  const act = p.id === activeSystemPromptId;
                  return (
                    <button
                      key={p.id}
                      type="button"
                      onClick={() => selectPrompt(p.id)}
                      className={cn(
                        "flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-[11.5px] transition-colors",
                        sel ? "bg-ember-soft text-bone" : "text-bone-dim hover:bg-ground-2 hover:text-bone"
                      )}
                    >
                      <span className={cn("size-1.5 shrink-0 rounded-full", act ? "bg-ember" : "bg-transparent border border-bone-muted")} />
                      <span className="min-w-0 flex-1 truncate">{p.name}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          {/* editor */}
          <div className="flex min-h-0 flex-1 flex-col">
            {selectedPrompt || creating ? (
              <>
                <div className="flex shrink-0 items-center gap-2 border-b border-rule px-4 py-2.5">
                  <div className="min-w-0 flex-1">
                    {editing ? (
                      <input
                        value={draftName}
                        onChange={(e) => setDraftName(e.target.value)}
                        className="w-full rounded border border-rule bg-ground-2 px-2 py-1 text-sm text-bone outline-none focus:border-ember/60"
                        placeholder="Prompt name"
                      />
                    ) : (
                      <span className="font-display text-lg italic text-bone">
                        {selectedPrompt?.name}
                      </span>
                    )}
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    {!isActive && !creating && !editing && (
                      <button
                        type="button"
                        onClick={activate}
                        className="rounded border border-rule px-2 py-1 font-mono text-[11px] text-bone-muted hover:bg-ground-2 hover:text-bone"
                      >
                        activate
                      </button>
                    )}
                    {!editing ? (
                      <button
                        type="button"
                        onClick={() => setEditing(true)}
                        className="rounded border border-rule px-2 py-1 font-mono text-[11px] text-bone-muted hover:bg-ground-2 hover:text-bone"
                      >
                        edit
                      </button>
                    ) : (
                      <>
                        <button
                          type="button"
                          onClick={() => { setEditing(false); setCreating(false); }}
                          className="rounded px-2 py-1 font-mono text-[11px] text-bone-muted hover:bg-ground-2 hover:text-bone"
                        >
                          cancel
                        </button>
                        <button
                          type="button"
                          onClick={() => save().catch(() => undefined)}
                          className="rounded bg-ember px-2 py-1 font-mono text-[11px] text-ground hover:opacity-90"
                        >
                          save
                        </button>
                      </>
                    )}
                  </div>
                </div>

                <div className="min-h-0 flex-1 p-4">
                  {editing ? (
                    <textarea
                      value={draftContent}
                      onChange={(e) => setDraftContent(e.target.value)}
                      className="h-full w-full resize-none rounded border border-rule bg-ground-2 px-3 py-2.5 font-mono text-[11.5px] leading-relaxed text-bone outline-none focus:border-ember/60"
                      placeholder="System prompt content…"
                    />
                  ) : (
                    <pre className="h-full overflow-auto whitespace-pre-wrap rounded bg-ground-2/60 p-3 font-mono text-[11.5px] leading-relaxed text-bone-dim">
                      {selectedPrompt?.content}
                    </pre>
                  )}
                </div>

                {isActive && !editing && (
                  <div className="shrink-0 border-t border-rule px-4 py-2">
                    <span className="font-mono text-[10.5px] text-ember">active for this conversation</span>
                  </div>
                )}
              </>
            ) : (
              <div className="flex h-full items-center justify-center text-sm text-bone-muted">
                select a prompt
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
