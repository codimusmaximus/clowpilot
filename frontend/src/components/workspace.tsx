"use client";

import { useEffect, useMemo, useRef } from "react";
import { X, FileText, Sparkles } from "lucide-react";
import { cn } from "@/lib/cn";
import { useWorkspace } from "@/lib/workspace-store";
import type { FileTab, Highlight, SnippetTab, Tab } from "@/lib/types";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import rehypeRaw from "rehype-raw";

function tabTitle(tab: Tab) {
  if (tab.kind === "file") return tab.path.split("/").pop() ?? tab.path;
  return tab.title;
}

function TabIcon({ tab }: { tab: Tab }) {
  if (tab.kind === "file")
    return <FileText className="size-3" strokeWidth={1.6} />;
  return <Sparkles className="size-3" strokeWidth={1.6} />;
}

export function Workspace() {
  const tabs = useWorkspace((s) => s.tabs);
  const activeTabId = useWorkspace((s) => s.activeTabId);
  const setActive = useWorkspace((s) => s.setActive);
  const closeTab = useWorkspace((s) => s.closeTab);
  const highlights = useWorkspace((s) => s.highlights);

  const activeTab = useMemo(
    () => tabs.find((t) => t.id === activeTabId) ?? tabs[0] ?? null,
    [tabs, activeTabId]
  );

  return (
    <div className="flex h-full min-h-0 flex-col bg-ground-2/30">
      <header className="flex shrink-0 items-center gap-3 border-b border-rule px-5 py-3">
        <span className="size-1.5 rounded-full bg-bone-muted" />
        <span className="font-display italic text-base text-bone">
          workspace
        </span>
        <span className="smallcaps">surfaced artefacts</span>
      </header>

      {tabs.length > 0 && (
        <div className="flex shrink-0 items-stretch overflow-x-auto border-b border-rule">
          {tabs.map((t) => {
            const active = activeTab?.id === t.id;
            return (
              <div
                key={t.id}
                className={cn(
                  "group relative flex items-center gap-2 border-r border-rule px-3.5 py-2 text-xs",
                  active
                    ? "bg-ground text-bone"
                    : "text-bone-dim hover:bg-ground/60 hover:text-bone"
                )}
              >
                <button
                  type="button"
                  onClick={() => setActive(t.id)}
                  className="flex items-center gap-2"
                >
                  <TabIcon tab={t} />
                  <span className="font-mono text-[11.5px]">{tabTitle(t)}</span>
                </button>
                <button
                  type="button"
                  aria-label="close"
                  onClick={() => closeTab(t.id)}
                  className="opacity-0 transition-opacity hover:text-ember group-hover:opacity-100"
                >
                  <X className="size-3" strokeWidth={1.8} />
                </button>
                {active && (
                  <span className="absolute inset-x-2 -bottom-px h-px bg-ember" />
                )}
              </div>
            );
          })}
        </div>
      )}

      <div className="min-h-0 flex-1 overflow-hidden">
        {!activeTab && <WorkspaceEmpty />}
        {activeTab?.kind === "file" && (
          <FileViewer
            tab={activeTab}
            highlights={highlights.filter((h) => h.path === activeTab.path)}
          />
        )}
        {activeTab?.kind === "snippet" && <SnippetView tab={activeTab} />}
      </div>
    </div>
  );
}

function WorkspaceEmpty() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-4 px-8 text-center">
      <div className="grid size-14 place-items-center rounded-full border border-rule">
        <Sparkles className="size-5 text-bone-muted" strokeWidth={1.4} />
      </div>
      <div className="space-y-1.5">
        <h2 className="font-display text-2xl italic text-bone">
          nothing surfaced yet
        </h2>
        <p className="max-w-sm text-sm text-bone-dim">
          When the assistant displays a file, highlights a passage, or renders
          an ad-hoc snippet, it appears here as a tab.
        </p>
      </div>
    </div>
  );
}

/* ─── file viewer ───────────────────────────────────────────────────── */

function FileViewer({ tab, highlights }: { tab: FileTab; highlights: Highlight[] }) {
  const lines = useMemo(() => tab.content.split("\n"), [tab.content]);

  // Build per-line highlight info
  const byLine = useMemo(() => {
    const map = new Map<number, Highlight[]>();
    for (const h of highlights) {
      for (let l = h.startLine; l <= h.endLine; l++) {
        const arr = map.get(l) ?? [];
        arr.push(h);
        map.set(l, arr);
      }
    }
    return map;
  }, [highlights]);

  // Map highlight start lines to comments aligned to their first line
  const startLines = useMemo(() => {
    const map = new Map<number, Highlight[]>();
    for (const h of highlights) {
      const arr = map.get(h.startLine) ?? [];
      arr.push(h);
      map.set(h.startLine, arr);
    }
    return map;
  }, [highlights]);

  // Track refs to lines so the comment column can absolute-position alongside
  const containerRef = useRef<HTMLDivElement>(null);
  const lineRefs = useRef<Map<number, HTMLDivElement | null>>(new Map());

  // scroll most-recent highlight into view
  useEffect(() => {
    if (highlights.length === 0) return;
    const newest = highlights[highlights.length - 1];
    const el = lineRefs.current.get(newest.startLine);
    el?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [highlights]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 items-center gap-2 border-b border-rule px-5 py-2 font-mono text-xs">
        <span className="smallcaps">path</span>
        <span className="text-bone-dim">{tab.path}</span>
        <span className="flex-1" />
        <span className="smallcaps">{tab.language}</span>
      </div>

      <div
        ref={containerRef}
        className="file-view relative flex-1 min-h-0 overflow-auto"
      >
        <div className="flex">
          {/* code column */}
          <div className="flex-1 min-w-0">
            {lines.map((line, i) => {
              const lineNum = i + 1;
              const isHl = byLine.has(lineNum);
              return (
                <div
                  key={i}
                  ref={(el) => {
                    lineRefs.current.set(lineNum, el);
                  }}
                  className={cn(
                    "row group flex font-mono text-[12.5px] leading-[1.65]",
                    isHl && "is-highlighted"
                  )}
                >
                  <div className="ln w-12 shrink-0 select-none px-3 text-right text-[11px]">
                    {lineNum}
                  </div>
                  <pre className="flex-1 overflow-x-auto whitespace-pre py-px pr-6">
                    <code>{line || "​"}</code>
                  </pre>
                </div>
              );
            })}
            <div className="h-24" />
          </div>

          {/* gutter / comment column */}
          <div className="hidden w-[22rem] shrink-0 border-l border-rule lg:block">
            <div className="sticky top-0 px-4 py-3">
              <span className="smallcaps">notes</span>
            </div>
            <div className="px-4">
              {highlights.length === 0 && (
                <p className="text-xs text-bone-muted">
                  No annotations yet. Ask the assistant to highlight a region.
                </p>
              )}
              {Array.from(startLines.entries())
                .sort(([a], [b]) => a - b)
                .map(([line, hs]) =>
                  hs.map((h) => (
                    <div
                      key={h.id}
                      className="mb-3 rounded border border-rule bg-ground-2/40 p-3"
                    >
                      <div className="mb-1.5 flex items-center gap-2">
                        <span className="size-1 rounded-full bg-ember" />
                        <span className="font-mono text-[10.5px] text-ember">
                          L{h.startLine}
                          {h.endLine !== h.startLine && `–${h.endLine}`}
                        </span>
                      </div>
                      <p className="text-[12.5px] leading-relaxed text-bone-dim">
                        {h.comment}
                      </p>
                    </div>
                  ))
                )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ─── snippet view ──────────────────────────────────────────────────── */

function SnippetView({ tab }: { tab: SnippetTab }) {
  return (
    <div className="h-full overflow-auto">
      <div className="mx-auto max-w-3xl px-10 py-12">
        {tab.format === "html" ? (
          <div
            className="prose-snippet"
            dangerouslySetInnerHTML={{ __html: tab.content }}
          />
        ) : (
          <div className="prose-snippet">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              rehypePlugins={[
                [rehypeHighlight, { detect: true, ignoreMissing: true }],
                rehypeRaw,
              ]}
            >
              {tab.content}
            </ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  );
}
