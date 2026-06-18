"use client";

import { createElement, useCallback, useEffect, useMemo, useState } from "react";
import { X, FileText, Sparkles, PanelRight, ChevronRight, Save } from "lucide-react";
import { useUIStore } from "@/lib/ui-store";
import { cn } from "@/lib/cn";
import { useWorkspace } from "@/lib/workspace-store";
import type { FileTab, Highlight, ImageTab, SnippetTab, Tab } from "@/lib/types";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import rehypeRaw from "rehype-raw";
import type { Components } from "react-markdown";
import { remarkWikiLinks, WorkspaceAnchor, WorkspaceImage } from "./markdown";
import { saveFile } from "@/lib/api";

function tabTitle(tab: Tab) {
  if (tab.kind === "file") return tab.path.split("/").pop() ?? tab.path;
  if (tab.kind === "image") return tab.path.split("/").pop() ?? tab.path;
  return tab.title;
}

function TabIcon({ tab }: { tab: Tab }) {
  if (tab.kind === "file")
    return <FileText className="size-3" strokeWidth={1.6} />;
  return <Sparkles className="size-3" strokeWidth={1.6} />;
}

function ImageViewer({ tab }: { tab: ImageTab }) {
  return (
    <div className="flex h-full items-center justify-center overflow-auto bg-ground p-6">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={tab.url}
        alt={tab.path}
        className="max-h-full max-w-full rounded object-contain shadow"
      />
    </div>
  );
}

export function Workspace() {
  // Restore persisted tabs/highlights on the client (store uses skipHydration).
  useEffect(() => {
    void useWorkspace.persist.rehydrate();
  }, []);

  const tabs = useWorkspace((s) => s.tabs);
  const activeTabId = useWorkspace((s) => s.activeTabId);
  const setActive = useWorkspace((s) => s.setActive);
  const closeTab = useWorkspace((s) => s.closeTab);
  const highlights = useWorkspace((s) => s.highlights);
  const removeHighlight = useWorkspace((s) => s.removeHighlight);
  const toggleRight = useUIStore((s) => s.toggleRight);

  const activeTab = useMemo(
    () => tabs.find((t) => t.id === activeTabId) ?? tabs[0] ?? null,
    [tabs, activeTabId]
  );

  return (
    <div className="flex h-full min-h-0 flex-col border-l border-rule bg-ground-2/20">
      <header className="flex h-[49px] shrink-0 items-center px-5">
        <span className="smallcaps">workspace</span>
        <span className="ml-2 font-mono text-[10.5px] text-bone-muted">
          {tabs.length === 0 ? "empty" : `${tabs.length} tab${tabs.length === 1 ? "" : "s"}`}
        </span>
        <span className="flex-1" />
        <button
          type="button"
          onClick={toggleRight}
          title="close workspace"
          aria-label="close workspace"
          className="rounded p-1.5 text-bone-muted hover:bg-ground-2 hover:text-bone"
        >
          <PanelRight className="size-4" strokeWidth={1.6} />
        </button>
      </header>

      {tabs.length > 0 && (
        <div className="flex shrink-0 items-stretch overflow-x-auto border-y border-rule bg-ground/35">
          {tabs.map((t) => {
            const active = activeTab?.id === t.id;
            return (
              <div
                key={t.id}
                className={cn(
                  "group relative flex items-center gap-2 border-r border-rule px-3.5 py-2 text-xs",
                  active
                    ? "bg-ground-2/80 text-bone"
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
                {active && <span className="absolute inset-x-0 -top-px h-px bg-ember/80" />}
              </div>
            );
          })}
        </div>
      )}

      <div className="min-h-0 flex-1 overflow-hidden">
        {!activeTab && <WorkspaceEmpty />}
        {activeTab?.kind === "file" && (
          <FileViewer
            key={activeTab.id}
            tab={activeTab}
            highlights={highlights.filter((h) => h.path === activeTab.path)}
            onRemoveHighlight={removeHighlight}
          />
        )}
        {activeTab?.kind === "image" && <ImageViewer tab={activeTab} />}
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

function FileViewer({
  tab,
  highlights,
  onRemoveHighlight,
}: {
  tab: FileTab;
  highlights: Highlight[];
  onRemoveHighlight: (id: string) => void;
}) {
  const lines = useMemo(() => tab.content.split("\n"), [tab.content]);
  const canRender = isRenderable(tab.language);
  const [mode, setMode] = useState<"raw" | "rendered">(
    canRender ? "rendered" : "raw"
  );
  const [draft, setDraft] = useState(tab.content);
  const [savedContent, setSavedContent] = useState(tab.content);
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved">("idle");
  const updateFileContent = useWorkspace((s) => s.updateFileContent);

  // Sync draft when the tab content changes externally (e.g. assistant edits)
  useEffect(() => {
    const id = window.setTimeout(() => {
      setDraft(tab.content);
      setSavedContent(tab.content);
      setSaveState("idle");
    }, 0);
    return () => window.clearTimeout(id);
  }, [tab.content]);

  const dirty = draft !== savedContent;

  const handleSave = useCallback(async (content: string) => {
    if (content === savedContent) return;
    setSaveState("saving");
    try {
      await saveFile(tab.path, content);
      setSavedContent(content);
      updateFileContent(tab.path, content);
      setSaveState("saved");
      setTimeout(() => setSaveState("idle"), 1500);
    } catch (err) {
      console.error("save failed", err);
      setSaveState("idle");
    }
  }, [savedContent, tab.path, updateFileContent]);

  // Auto-save 1.5 s after last keystroke
  useEffect(() => {
    if (draft === savedContent) return;
    const id = setTimeout(() => handleSave(draft), 1500);
    return () => clearTimeout(id);
  }, [draft, savedContent, handleSave]);

  // Cmd+S / Ctrl+S — immediate save
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "s") {
        e.preventDefault();
        handleSave(draft);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [draft, handleSave]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 items-center gap-2 px-5 py-2 font-mono text-xs text-bone-muted">
        <span className="smallcaps">path</span>
        <span>{tab.path}</span>
        <span className="flex-1" />
        {saveState === "saving" && (
          <span className="font-mono text-[10.5px] text-bone-muted">saving…</span>
        )}
        {saveState === "saved" && (
          <span className="font-mono text-[10.5px] text-ember/70">saved</span>
        )}
        {saveState === "idle" && dirty && (
          <button
            type="button"
            onClick={() => handleSave(draft)}
            className="flex items-center gap-1 font-mono text-[10.5px] text-bone-muted hover:text-bone"
            title="Save (⌘S)"
          >
            <Save className="size-3" strokeWidth={1.6} />
            unsaved
          </button>
        )}
        <span className="smallcaps">{tab.language}</span>
        {canRender && (
          <div className="ml-2 flex overflow-hidden rounded border border-rule text-[10.5px]">
            <button
              type="button"
              onClick={() => setMode("raw")}
              className={cn(
                "px-2 py-0.5 uppercase tracking-[0.16em]",
                mode === "raw"
                  ? "bg-ember text-ground"
                  : "text-bone-muted hover:bg-ground-2 hover:text-bone"
              )}
            >
              raw
            </button>
            <button
              type="button"
              onClick={() => setMode("rendered")}
              className={cn(
                "border-l border-rule px-2 py-0.5 uppercase tracking-[0.16em]",
                mode === "rendered"
                  ? "bg-ember text-ground"
                  : "text-bone-muted hover:bg-ground-2 hover:text-bone"
              )}
            >
              rendered
            </button>
          </div>
        )}
      </div>

      {canRender && mode === "rendered" ? (
        <RenderedFile
          tab={tab}
          highlights={highlights}
          lines={lines}
          onRemoveHighlight={onRemoveHighlight}
        />
      ) : (
        <div className="file-view flex-1 min-h-0 overflow-auto">
          <textarea
            className="h-full w-full resize-none bg-transparent font-mono text-[12.5px] leading-[1.65] text-bone-dim caret-ember outline-none px-5 py-3 placeholder:text-bone-muted"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            spellCheck={false}
            autoComplete="off"
            autoCorrect="off"
            autoCapitalize="off"
          />
        </div>
      )}
    </div>
  );
}

function isRenderable(language: string) {
  return ["markdown", "csv", "html", "json"].includes(language);
}

/* ─── frontmatter ───────────────────────────────────────────────────────── */

function parseFrontmatter(content: string): {
  meta: Record<string, string>;
  body: string;
} {
  const match = content.match(/^---\r?\n([\s\S]*?)\r?\n---[ \t]*\r?\n?/);
  if (!match) return { meta: {}, body: content };
  const meta: Record<string, string> = {};
  for (const line of match[1].split(/\r?\n/)) {
    const idx = line.indexOf(":");
    if (idx === -1) continue;
    const key = line.slice(0, idx).trim();
    const val = line.slice(idx + 1).trim().replace(/^["']|["']$/g, "");
    if (key) meta[key] = val;
  }
  return { meta, body: content.slice(match[0].length) };
}

function FrontmatterPanel({ meta }: { meta: Record<string, string> }) {
  const [open, setOpen] = useState(false);
  const entries = Object.entries(meta);
  if (entries.length === 0) return null;

  return (
    <div className="mb-6 rounded border border-rule/70 bg-ground-2/50 text-[12px]">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-1.5 px-3 py-2 text-left"
      >
        <ChevronRight
          className={cn(
            "size-3 shrink-0 text-bone-muted/60 transition-transform",
            open && "rotate-90"
          )}
          strokeWidth={1.6}
        />
        <span className="font-mono text-[10.5px] text-bone-muted">properties</span>
        {!open && (
          <span className="ml-1 truncate font-mono text-[10px] text-bone-muted/50">
            {entries
              .slice(0, 4)
              .map(([k]) => k)
              .join(", ")}
            {entries.length > 4 ? "…" : ""}
          </span>
        )}
      </button>
      {open && (
        <div className="border-t border-rule/50 px-3 pb-3 pt-2">
          <dl className="space-y-1.5">
            {entries.map(([k, v]) => (
              <div key={k} className="flex gap-3">
                <dt className="w-28 shrink-0 font-mono text-[11px] text-bone-muted">{k}</dt>
                <dd className="min-w-0 flex-1 break-words text-[11.5px] text-bone-dim">{v}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}
    </div>
  );
}

function RenderedFile({
  tab,
  highlights,
  lines,
  onRemoveHighlight,
}: {
  tab: FileTab;
  highlights: Highlight[];
  lines: string[];
  onRemoveHighlight: (id: string) => void;
}) {
  if (tab.language === "markdown") {
    const { meta, body } = parseFrontmatter(tab.content);
    return (
      <div className="flex min-h-0 flex-1 overflow-hidden">
        <div className="min-w-0 flex-1 overflow-auto">
          <div className="prose-snippet min-h-full max-w-none px-10 py-8">
            <FrontmatterPanel meta={meta} />
            <ReactMarkdown
              remarkPlugins={[remarkGfm, remarkWikiLinks]}
              rehypePlugins={[
                [rehypeHighlight, { detect: true, ignoreMissing: true }],
                rehypeRaw,
              ]}
              components={{
                ...markdownHighlightComponents(highlights, onRemoveHighlight),
                a: WorkspaceAnchor,
                img: WorkspaceImage,
              }}
            >
              {body}
            </ReactMarkdown>
          </div>
        </div>
        {highlights.length > 0 && (
          <RenderedHighlightRail
            highlights={highlights}
            lines={lines}
            onRemoveHighlight={onRemoveHighlight}
          />
        )}
      </div>
    );
  }

  if (tab.language === "csv") {
    return (
      <CsvView
        content={tab.content}
        highlights={highlights}
        lines={lines}
        onRemoveHighlight={onRemoveHighlight}
      />
    );
  }

  if (tab.language === "html") {
    return (
      <div className="flex min-h-0 flex-1 overflow-hidden">
        <div className="min-w-0 flex-1 overflow-auto">
          <div
            className="prose-snippet min-h-full max-w-none px-10 py-8"
            dangerouslySetInnerHTML={{ __html: tab.content }}
          />
        </div>
        {highlights.length > 0 && (
          <RenderedHighlightRail
            highlights={highlights}
            lines={lines}
            onRemoveHighlight={onRemoveHighlight}
          />
        )}
      </div>
    );
  }

  if (tab.language === "json") {
    const formatted = formatJson(tab.content);
    if (formatted === null) {
      return <RawRenderFallback content="Invalid JSON; switch to raw view." />;
    }
    return (
      <div className="flex min-h-0 flex-1 overflow-hidden">
        <div className="file-view min-w-0 flex-1 overflow-auto p-5">
          <pre className="font-mono text-xs leading-relaxed text-bone-dim">
            {formatted}
          </pre>
        </div>
        {highlights.length > 0 && (
          <RenderedHighlightRail
            highlights={highlights}
            lines={lines}
            onRemoveHighlight={onRemoveHighlight}
          />
        )}
      </div>
    );
  }

  return <RawRenderFallback content="No rendered view for this file type." />;
}

function formatJson(content: string) {
  try {
    return JSON.stringify(JSON.parse(content), null, 2);
  } catch {
    return null;
  }
}

function overlapsHighlight(
  position: { start?: { line?: number }; end?: { line?: number } } | undefined,
  highlights: Highlight[]
) {
  const start = position?.start?.line;
  const end = position?.end?.line ?? start;
  if (!start || !end) return null;
  return highlights.find((h) => start <= h.endLine && end >= h.startLine) ?? null;
}

function markdownHighlightComponents(
  highlights: Highlight[],
  onRemoveHighlight: (id: string) => void
): Components {
  type HighlightTag =
    | "p"
    | "h1"
    | "h2"
    | "h3"
    | "h4"
    | "h5"
    | "h6"
    | "li"
    | "blockquote"
    | "pre"
    | "table";
  const wrap = (Tag: HighlightTag) => {
    type MarkdownNodeProps = React.HTMLAttributes<HTMLElement> & {
      node?: { position?: { start?: { line?: number }; end?: { line?: number } } };
      children?: React.ReactNode;
    };
    const Component = ({ node, children, ...props }: MarkdownNodeProps) => {
      const highlight = overlapsHighlight(node?.position, highlights);
      const content = createElement(Tag, props, children);
      if (!highlight) return content;
      return (
        <div className="render-highlight group relative -mx-3 rounded border border-ember/25 bg-ember-soft/55 px-3 py-1.5">
          <div className="absolute -left-2 top-2 h-[calc(100%-1rem)] w-1 rounded-full bg-ember" />
          {content}
          <div className="mt-1.5 border-t border-ember/20 pt-1.5 text-[11.5px] leading-relaxed text-bone-dim opacity-90">
            <span className="font-mono text-ember">
              L{highlight.startLine}
              {highlight.endLine !== highlight.startLine && `–${highlight.endLine}`}
            </span>{" "}
            {highlight.comment}
            <button
              type="button"
              aria-label="close annotation"
              onClick={() => onRemoveHighlight(highlight.id)}
              title="Close annotation"
              className="ml-2 inline-flex rounded border border-rule bg-ground/70 p-0.5 text-bone-muted hover:border-ember/40 hover:text-bone"
            >
              <X className="size-3" strokeWidth={1.6} />
            </button>
          </div>
        </div>
      );
    };
    return Component;
  };

  return {
    p: wrap("p"),
    h1: wrap("h1"),
    h2: wrap("h2"),
    h3: wrap("h3"),
    h4: wrap("h4"),
    h5: wrap("h5"),
    h6: wrap("h6"),
    li: wrap("li"),
    blockquote: wrap("blockquote"),
    pre: wrap("pre"),
    table: wrap("table"),
  };
}

function CsvView({
  content,
  highlights,
  lines,
  onRemoveHighlight,
}: {
  content: string;
  highlights: Highlight[];
  lines: string[];
  onRemoveHighlight: (id: string) => void;
}) {
  const rows = useMemo(() => parseCsv(content), [content]);
  const highlightedLines = useMemo(() => {
    const set = new Set<number>();
    for (const h of highlights) {
      for (let line = h.startLine; line <= h.endLine; line++) set.add(line);
    }
    return set;
  }, [highlights]);
  if (rows.length === 0) return <RawRenderFallback content="Empty CSV." />;
  const [headers, ...body] = rows;
  return (
    <div className="flex min-h-0 flex-1 overflow-hidden">
      <div className="min-w-0 flex-1 overflow-auto p-5">
        <table className="w-full border-collapse text-left text-xs">
          <thead className="sticky top-0 bg-ground">
            <tr className={cn(highlightedLines.has(1) && "bg-ember-soft") }>
              {headers.map((cell, i) => (
                <th
                  key={i}
                  className="border border-rule bg-ground-2/60 px-3 py-2 font-mono text-[10.5px] uppercase tracking-[0.16em] text-bone-muted"
                >
                  {cell}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {body.map((row, i) => {
              const sourceLine = i + 2;
              return (
                <tr
                  key={i}
                  className={cn(
                    "odd:bg-ground-2/20",
                    highlightedLines.has(sourceLine) && "bg-ember-soft outline outline-1 outline-ember/30"
                  )}
                >
                  {headers.map((_, j) => (
                    <td key={j} className="border border-rule px-3 py-2 text-bone-dim">
                      {row[j] ?? ""}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {highlights.length > 0 && (
        <RenderedHighlightRail
          highlights={highlights}
          lines={lines}
          onRemoveHighlight={onRemoveHighlight}
        />
      )}
    </div>
  );
}

function RenderedHighlightRail({
  highlights,
  lines,
  onRemoveHighlight,
}: {
  highlights: Highlight[];
  lines: string[];
  onRemoveHighlight: (id: string) => void;
}) {
  return (
    <aside className="hidden w-[22rem] shrink-0 overflow-auto border-l border-rule lg:block">
      <div className="sticky top-0 bg-ground-2/95 px-4 py-3 backdrop-blur">
        <span className="smallcaps">annotations</span>
      </div>
      <div className="px-4 pb-6">
        {highlights.map((h) => (
          <div
            key={h.id}
            className="mb-3 rounded border border-ember/25 bg-ember-soft/60 p-3"
          >
            <div className="mb-2 flex items-center gap-2">
              <span className="size-1 rounded-full bg-ember" />
              <span className="font-mono text-[10.5px] text-ember">
                L{h.startLine}
                {h.endLine !== h.startLine && `–${h.endLine}`}
              </span>
              <button
                type="button"
                aria-label="close annotation"
                title="Close annotation"
                onClick={() => onRemoveHighlight(h.id)}
                className="ml-auto rounded border border-rule bg-ground/70 p-0.5 text-bone-muted hover:border-ember/40 hover:text-bone"
              >
                <X className="size-3" strokeWidth={1.6} />
              </button>
            </div>
            <pre className="mb-2 max-h-28 overflow-auto whitespace-pre-wrap rounded bg-ground/50 p-2 font-mono text-[10.5px] leading-relaxed text-bone-dim">
              {lines.slice(h.startLine - 1, h.endLine).join("\n")}
            </pre>
            <p className="text-[12.5px] leading-relaxed text-bone-dim">
              {h.comment}
            </p>
          </div>
        ))}
      </div>
    </aside>
  );
}

function RawRenderFallback({ content }: { content: string }) {
  return (
    <div className="flex h-full items-center justify-center px-6 text-center text-sm text-bone-muted">
      {content}
    </div>
  );
}

function parseCsv(content: string) {
  return content
    .trim()
    .split(/\r?\n/)
    .map((line) => {
      const cells: string[] = [];
      let cell = "";
      let quoted = false;
      for (let i = 0; i < line.length; i++) {
        const char = line[i];
        const next = line[i + 1];
        if (char === '"' && quoted && next === '"') {
          cell += '"';
          i++;
        } else if (char === '"') {
          quoted = !quoted;
        } else if (char === "," && !quoted) {
          cells.push(cell);
          cell = "";
        } else {
          cell += char;
        }
      }
      cells.push(cell);
      return cells;
    });
}

/* ─── rehype plugin: strip <script> so raw HTML is safe in markdown ─── */

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function stripScripts(node: any) {
  if (!Array.isArray(node.children)) return;
  node.children = node.children.filter(
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (c: any) => !(c.type === "element" && c.tagName === "script")
  );
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  node.children.forEach((c: any) => stripScripts(c));
}
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const rehypeStripScripts = () => (tree: any) => stripScripts(tree);

/* ─── snippet view ──────────────────────────────────────────────────── */

function SnippetView({ tab }: { tab: SnippetTab }) {
  return (
    <div className="h-full overflow-auto">
      <div className="mx-auto max-w-3xl px-10 py-12">
        {tab.format === "html" ? (
          <iframe
            srcDoc={tab.content}
            sandbox="allow-scripts"
            className="h-[600px] w-full rounded border border-rule bg-white"
            title={tab.title}
          />
        ) : (
          <div className="prose-snippet">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              rehypePlugins={[
                [rehypeHighlight, { detect: true, ignoreMissing: true }],
                rehypeRaw,
                rehypeStripScripts,
              ]}
              components={{ a: WorkspaceAnchor, img: WorkspaceImage }}
            >
              {tab.content}
            </ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  );
}
