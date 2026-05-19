"use client";

import { useEffect, useState } from "react";
import { Copy, Settings, X } from "lucide-react";
import { useChatStore } from "@/lib/chat-store";
import { useUIStore } from "@/lib/ui-store";
import { fetchSessionInfo, type SessionInfo } from "@/lib/api";

export function SessionInfoModal() {
  const open = useUIStore((s) => s.sessionInfoOpen);
  if (!open) return null;
  return <SessionInfoContent />;
}

function SessionInfoContent() {
  const close = useUIStore((s) => s.closeSessionInfo);
  const conversationId = useChatStore((s) => s.activeConversationId);

  const [info, setInfo] = useState<SessionInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setInfo(null);
    setError(null);
    if (!conversationId) {
      setError("No active conversation. Open or start a chat first.");
      return;
    }
    fetchSessionInfo(conversationId)
      .then((data) => {
        if (!cancelled) setInfo(data);
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, [conversationId]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [close]);

  const copyPrompt = async () => {
    if (!info?.systemPrompt) return;
    try {
      await navigator.clipboard.writeText(info.systemPrompt);
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch {
      /* ignored */
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={(e) => {
        if (e.target === e.currentTarget) close();
      }}
    >
      <div className="flex h-[80vh] w-full max-w-3xl flex-col rounded border border-rule bg-ground shadow-2xl mx-4">
        <div className="flex shrink-0 items-center gap-3 border-b border-rule px-5 py-3.5">
          <Settings className="size-4 text-ember" strokeWidth={1.6} />
          <span className="smallcaps">session info</span>
          {info && (
            <span className="font-mono text-[11px] text-bone-muted">
              {info.model.split(":").slice(-1)[0]}
            </span>
          )}
          <span className="flex-1" />
          <button
            type="button"
            aria-label="close"
            onClick={close}
            className="rounded p-1 text-bone-muted hover:bg-ground-2 hover:text-bone"
          >
            <X className="size-4" strokeWidth={1.6} />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4 text-sm">
          {error && (
            <p className="rounded border border-rule bg-ground-2/40 px-3 py-2 text-bone-muted">
              {error}
            </p>
          )}
          {!error && !info && (
            <p className="text-bone-muted">Loading…</p>
          )}
          {info && (
            <div className="space-y-5">
              <Section label="active model">
                <code className="font-mono text-[11.5px] text-bone">{info.model}</code>
              </Section>

              <Section
                label={`base prompt · ${info.basePrompt.name}`}
                count={`~${Math.max(1, Math.floor(info.basePrompt.content.length / 4)).toLocaleString()} tok`}
              >
                <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded border border-rule bg-ground-2/40 p-2.5 font-mono text-[11px] leading-relaxed text-bone-dim">
                  {info.basePrompt.content}
                </pre>
              </Section>

              <Section label="project" count={info.project?.name ?? "(none)"}>
                {info.project ? (
                  <>
                    <div className="mb-2 flex items-center gap-2 font-mono text-[11px] text-bone-muted">
                      <span>id: {info.project.id}</span>
                      {info.knowledge && (
                        <span className="rounded bg-ground-2 px-1 text-[10px]">
                          mode: {info.knowledge.mode}
                          {info.knowledge.mode === "preview"
                            ? ` (${info.knowledge.preview_tokens} tok/file)`
                            : ""}
                        </span>
                      )}
                    </div>

                    {/* Raw pinned items */}
                    {info.knowledgeLinks && info.knowledgeLinks.length > 0 ? (
                      <div className="mb-3">
                        <div className="mb-1 text-[10.5px] text-bone-muted">
                          pinned ({info.knowledgeLinks.length})
                        </div>
                        <ul className="space-y-1">
                          {info.knowledgeLinks.map((l) => (
                            <li key={l.id} className="flex items-center gap-2">
                              <span className="rounded bg-ground-2 px-1 font-mono text-[10px] text-bone-muted">
                                {l.ref_type === "page_folder" ? "folder" : "page"}
                              </span>
                              <span className="font-mono text-[11px] text-bone-dim">
                                {l.ref_path}
                              </span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : (
                      <p className="text-xs text-bone-muted">no knowledge pinned</p>
                    )}

                    {/* Expansion result */}
                    {info.knowledgeLinks && info.knowledgeLinks.length > 0 && (
                      <>
                        <div className="mb-1 text-[10.5px] text-bone-muted">
                          inlined into the prompt
                          {info.knowledge && info.knowledge.included.length === 0
                            ? " (none — folder had no .md files)"
                            : ""}
                        </div>
                        {info.knowledge && (info.knowledge.included.length > 0 || info.knowledge.truncated.length > 0) ? (
                          <ul className="divide-y divide-rule border-y border-rule">
                            {info.knowledge.included.map((k) => (
                              <li
                                key={`in-${k.ref_path}`}
                                className="flex items-center gap-2 py-1.5"
                              >
                                <span className="rounded bg-ember-soft px-1 font-mono text-[10px] text-ember">
                                  inlined
                                </span>
                                <span className="min-w-0 flex-1 truncate font-mono text-[11px] text-bone-dim">
                                  {k.ref_path}
                                </span>
                                <span className="font-mono text-[10px] text-bone-muted">
                                  {k.tokens.toLocaleString()} tok
                                </span>
                              </li>
                            ))}
                            {info.knowledge.truncated.map((k) => (
                              <li
                                key={`tr-${k.ref_path}`}
                                className="flex items-center gap-2 py-1.5"
                              >
                                <span className="rounded bg-ground-2 px-1 font-mono text-[10px] text-red-400">
                                  {k.reason}
                                </span>
                                <span className="min-w-0 flex-1 truncate font-mono text-[11px] text-bone-muted">
                                  {k.ref_path}
                                </span>
                                <span className="font-mono text-[10px] text-bone-muted">
                                  ~{k.tokens.toLocaleString()} tok
                                </span>
                              </li>
                            ))}
                          </ul>
                        ) : null}
                        {info.knowledge && info.knowledge.total_tokens > 0 && (
                          <p className="mt-2 text-[10.5px] text-bone-muted">
                            inlined: {info.knowledge.total_tokens.toLocaleString()} / {info.knowledge.max_tokens.toLocaleString()} tok cap
                          </p>
                        )}
                      </>
                    )}
                  </>
                ) : (
                  <p className="text-xs text-bone-muted">
                    this chat is not in a project
                  </p>
                )}
              </Section>

              <Section
                label="plugins enabled"
                count={`${info.plugins.filter((p) => p.enabled).length} of ${info.plugins.length}`}
              >
                <ul className="space-y-1">
                  {info.plugins.map((p) => (
                    <li key={p.id} className="flex items-center gap-2">
                      <span
                        className={`size-1.5 rounded-full ${p.enabled ? "bg-ember" : "bg-bone-muted/40"}`}
                      />
                      <span className="font-mono text-[11px] text-bone-dim">
                        {p.name}
                      </span>
                      <span className="font-mono text-[10px] text-bone-muted">
                        {
                          Object.values(p.toolsEnabled ?? {}).filter(Boolean).length
                        }/{p.tools?.length ?? 0} tools
                      </span>
                    </li>
                  ))}
                </ul>
              </Section>

              <Section
                label="composed system prompt (what the model sees)"
                count={`~${info.systemPromptTokens.toLocaleString()} tok · ${info.systemPromptBytes.toLocaleString()} bytes`}
                action={
                  <button
                    type="button"
                    onClick={copyPrompt}
                    className="flex items-center gap-1 rounded border border-rule px-2 py-0.5 text-[10.5px] text-bone-dim hover:bg-ground-2 hover:text-bone"
                  >
                    <Copy className="size-2.5" strokeWidth={1.6} />
                    {copied ? "copied" : "copy"}
                  </button>
                }
              >
                <pre className="max-h-[40vh] overflow-auto whitespace-pre-wrap rounded border border-rule bg-ground-2/40 p-2.5 font-mono text-[11px] leading-relaxed text-bone-dim">
                  {info.systemPrompt}
                </pre>
              </Section>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Section({
  label,
  count,
  action,
  children,
}: {
  label: string;
  count?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section>
      <div className="mb-2 flex items-center gap-2">
        <span className="smallcaps">{label}</span>
        {count && (
          <span className="font-mono text-[10.5px] text-bone-muted">{count}</span>
        )}
        <span className="flex-1" />
        {action}
      </div>
      {children}
    </section>
  );
}
