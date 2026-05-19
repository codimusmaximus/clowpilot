"use client";

import { useEffect, useMemo, useState } from "react";
import { ChevronDown, ChevronRight, FileText, Folder, X } from "lucide-react";
import { useChatStore } from "@/lib/chat-store";
import { useUIStore } from "@/lib/ui-store";
import { fetchPageTree } from "@/lib/api";
import type { FileNode } from "@/lib/types";
import type { ProjectKnowledgeRefType } from "@/lib/api";

type Selection = { refType: ProjectKnowledgeRefType; refPath: string };
const selKey = (s: Selection) => `${s.refType}:${s.refPath}`;
const EMPTY_LINKS: never[] = [];

export function KnowledgePicker() {
  const projectId = useUIStore((s) => s.knowledgePickerProjectId);
  if (!projectId) return null;
  return <KnowledgePickerContent projectId={projectId} />;
}

function KnowledgePickerContent({ projectId }: { projectId: string }) {
  const close = useUIStore((s) => s.closeKnowledgePicker);
  const project = useChatStore((s) => s.projects.find((p) => p.id === projectId));
  const existingLinks =
    useChatStore((s) => s.projectKnowledge[projectId]) ?? EMPTY_LINKS;
  const loadKnowledge = useChatStore((s) => s.loadProjectKnowledge);
  const addKnowledge = useChatStore((s) => s.addProjectKnowledge);
  const removeKnowledge = useChatStore((s) => s.removeProjectKnowledge);

  const [tree, setTree] = useState<FileNode | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set([""]));
  const [selected, setSelected] = useState<Map<string, Selection>>(new Map());
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    loadKnowledge(projectId).catch(() => undefined);
    fetchPageTree().then(setTree).catch(() => setTree(null));
  }, [projectId, loadKnowledge]);

  useEffect(() => {
    const next = new Map<string, Selection>();
    for (const l of existingLinks) {
      const sel: Selection = {
        refType: l.ref_type as ProjectKnowledgeRefType,
        refPath: l.ref_path,
      };
      next.set(selKey(sel), sel);
    }
    setSelected(next);
  }, [existingLinks]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [close]);

  const toggleExpand = (path: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  const toggleSelect = (refType: ProjectKnowledgeRefType, refPath: string) => {
    const sel = { refType, refPath };
    const key = selKey(sel);
    setSelected((prev) => {
      const next = new Map(prev);
      if (next.has(key)) next.delete(key);
      else next.set(key, sel);
      return next;
    });
  };

  const existingKeys = useMemo(() => {
    const s = new Set<string>();
    for (const l of existingLinks) {
      s.add(selKey({ refType: l.ref_type as ProjectKnowledgeRefType, refPath: l.ref_path }));
    }
    return s;
  }, [existingLinks]);

  const save = async () => {
    setSaving(true);
    try {
      const selectedKeys = new Set(selected.keys());
      // links to add
      const toAdd = [...selected.values()].filter((s) => !existingKeys.has(selKey(s)));
      // links to remove (existing not in selection)
      const toRemove = existingLinks.filter(
        (l) =>
          !selectedKeys.has(
            selKey({ refType: l.ref_type as ProjectKnowledgeRefType, refPath: l.ref_path })
          )
      );
      for (const link of toRemove) {
        await removeKnowledge(projectId, link.id).catch(() => undefined);
      }
      for (const s of toAdd) {
        await addKnowledge(projectId, s.refType, s.refPath).catch(() => undefined);
      }
    } finally {
      setSaving(false);
      close();
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={(e) => {
        if (e.target === e.currentTarget) close();
      }}
    >
      <div className="flex h-[600px] w-full max-w-xl flex-col rounded border border-rule bg-ground shadow-2xl mx-4">
        <div className="flex shrink-0 items-center gap-3 border-b border-rule px-5 py-3.5">
          <span className="size-1.5 rounded-full bg-ember" />
          <span className="smallcaps">knowledge</span>
          <span className="text-xs text-bone-muted">
            {project?.name ?? "project"}
          </span>
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

        <div className="min-h-0 flex-1 overflow-y-auto px-2 py-2 text-sm">
          {tree === null ? (
            <div className="px-3 py-2 text-xs text-bone-muted">Loading pages…</div>
          ) : (
            <TreeNode
              node={tree}
              depth={0}
              isRoot
              expanded={expanded}
              selected={selected}
              onToggleExpand={toggleExpand}
              onToggleSelect={toggleSelect}
            />
          )}
        </div>

        <div className="flex shrink-0 items-center gap-3 border-t border-rule px-5 py-3">
          <span className="text-xs text-bone-muted">
            {selected.size} pinned
          </span>
          <span className="flex-1" />
          <button
            type="button"
            onClick={close}
            className="rounded border border-rule px-3 py-1 text-xs text-bone-dim hover:bg-ground-2 hover:text-bone"
          >
            cancel
          </button>
          <button
            type="button"
            onClick={save}
            disabled={saving}
            className="rounded bg-ember px-3 py-1 text-xs text-ground hover:opacity-90 disabled:opacity-40"
          >
            {saving ? "saving…" : "save"}
          </button>
        </div>
      </div>
    </div>
  );
}

function TreeNode({
  node,
  depth,
  isRoot,
  expanded,
  selected,
  onToggleExpand,
  onToggleSelect,
}: {
  node: FileNode;
  depth: number;
  isRoot?: boolean;
  expanded: Set<string>;
  selected: Map<string, Selection>;
  onToggleExpand: (path: string) => void;
  onToggleSelect: (refType: ProjectKnowledgeRefType, refPath: string) => void;
}) {
  const isDir = node.type === "dir";
  const isOpen = expanded.has(node.path) || isRoot;
  const indent = { paddingLeft: `${depth * 14 + 8}px` };

  if (isRoot) {
    return (
      <div>
        {(node.children ?? []).map((child) => (
          <TreeNode
            key={child.path}
            node={child}
            depth={depth}
            expanded={expanded}
            selected={selected}
            onToggleExpand={onToggleExpand}
            onToggleSelect={onToggleSelect}
          />
        ))}
      </div>
    );
  }

  const refType: ProjectKnowledgeRefType = isDir ? "page_folder" : "page";
  const key = selKey({ refType, refPath: node.path });
  const isChecked = selected.has(key);

  return (
    <div>
      <div
        className="group flex items-center gap-1.5 rounded py-1 pr-2 hover:bg-ground-2"
        style={indent}
      >
        {isDir ? (
          <button
            type="button"
            onClick={() => onToggleExpand(node.path)}
            className="flex size-4 items-center justify-center text-bone-muted hover:text-bone"
          >
            {isOpen ? (
              <ChevronDown className="size-3" strokeWidth={1.6} />
            ) : (
              <ChevronRight className="size-3" strokeWidth={1.6} />
            )}
          </button>
        ) : (
          <span className="inline-block size-4" />
        )}
        <input
          type="checkbox"
          checked={isChecked}
          onChange={() => onToggleSelect(refType, node.path)}
          className="size-3 accent-ember"
          aria-label={`pin ${node.path}`}
        />
        {isDir ? (
          <Folder className="size-3.5 text-bone-muted" strokeWidth={1.6} />
        ) : (
          <FileText className="size-3.5 text-bone-muted" strokeWidth={1.6} />
        )}
        <span className="truncate font-mono text-[11px] text-bone">{node.name}</span>
      </div>
      {isDir && isOpen && (node.children ?? []).map((child) => (
        <TreeNode
          key={child.path}
          node={child}
          depth={depth + 1}
          expanded={expanded}
          selected={selected}
          onToggleExpand={onToggleExpand}
          onToggleSelect={onToggleSelect}
        />
      ))}
    </div>
  );
}
