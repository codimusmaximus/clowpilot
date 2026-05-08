"use client";

import { useEffect, useState } from "react";
import {
  Folder,
  FolderOpen,
  ChevronRight,
  FileText,
  RefreshCw,
  Plus,
} from "lucide-react";
import { cn } from "@/lib/cn";
import { useWorkspace } from "@/lib/workspace-store";
import { useChatStore } from "@/lib/chat-store";
import { fetchTree, fetchFile, uploadFile } from "@/lib/api";
import type { FileNode } from "@/lib/types";
import { ResizableSplit } from "./resizable-split";

export function Sidebar() {
  const tree = useWorkspace((s) => s.tree);
  const setTree = useWorkspace((s) => s.setTree);
  const setLoading = useWorkspace((s) => s.setTreeLoading);
  const loading = useWorkspace((s) => s.treeLoading);
  const openFile = useWorkspace((s) => s.openFile);
  const conversations = useChatStore((s) => s.conversations);
  const activeConversationId = useChatStore((s) => s.activeConversationId);
  const isRunning = useChatStore((s) => s.isRunning);
  const newConversation = useChatStore((s) => s.newConversation);
  const selectConversation = useChatStore((s) => s.selectConversation);

  const refresh = async () => {
    setLoading(true);
    try {
      const t = await fetchTree();
      setTree(t);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 4000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    await uploadFile(f);
    await refresh();
    e.target.value = "";
  };

  const handleOpenFile = async (path: string) => {
    try {
      const f = await fetchFile(path);
      openFile(f.path, f.content, f.kind);
    } catch (err) {
      console.error(err);
    }
  };

  const threadsPanel = (
    <div className="flex h-full flex-col px-4 pt-3 pb-1">
      <div className="flex items-center gap-2 shrink-0">
        <span className="smallcaps flex-1">threads</span>
        <button
          type="button"
          aria-label="new chat"
          title="new chat"
          disabled={isRunning}
          onClick={() => newConversation().catch(() => undefined)}
          className="rounded p-1 text-bone-muted hover:bg-ground hover:text-bone disabled:opacity-40"
        >
          <Plus className="size-3" strokeWidth={1.6} />
        </button>
      </div>
      <ul className="mt-1.5 min-h-0 flex-1 space-y-1 overflow-y-auto">
        {conversations.map((conversation) => {
          const active = conversation.id === activeConversationId;
          return (
            <li key={conversation.id}>
              <button
                type="button"
                disabled={isRunning}
                onClick={() =>
                  selectConversation(conversation.id).catch(() => undefined)
                }
                className={cn(
                  "flex w-full items-center gap-2 rounded border px-2.5 py-1.5 text-left disabled:opacity-40",
                  active
                    ? "border-rule bg-ground/60 text-bone"
                    : "border-transparent text-bone-dim hover:bg-ground/50 hover:text-bone"
                )}
              >
                <span
                  className={cn(
                    "size-1.5 shrink-0 rounded-full",
                    active ? "bg-ember" : "bg-bone-muted"
                  )}
                />
                <span className="min-w-0 flex-1 truncate text-[12px]">
                  {conversation.title}
                </span>
              </button>
            </li>
          );
        })}
        {conversations.length === 0 && (
          <li className="px-2.5 py-1 text-[11.5px] text-bone-muted">
            no chats yet
          </li>
        )}
      </ul>
    </div>
  );

  const workspacePanel = (
    <div className="flex h-full flex-col">
      <div className="flex shrink-0 items-center gap-2 px-4 pt-3 pb-2">
        <span className="smallcaps flex-1">workspace</span>
        <label
          className="cursor-pointer rounded p-1 text-bone-muted hover:bg-ground hover:text-bone"
          aria-label="upload"
          title="upload file"
        >
          <Plus className="size-3" strokeWidth={1.6} />
          <input type="file" className="hidden" onChange={onUpload} />
        </label>
        <button
          type="button"
          aria-label="refresh"
          title="refresh tree"
          onClick={refresh}
          className="rounded p-1 text-bone-muted hover:bg-ground hover:text-bone"
        >
          <RefreshCw
            className={cn(
              "size-3",
              loading && "animate-spin text-ember"
            )}
            strokeWidth={1.6}
          />
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-6">
        {tree ? (
          <TreeView node={tree} depth={0} onOpenFile={handleOpenFile} />
        ) : (
          <p className="px-3 py-2 text-xs text-bone-muted">loading…</p>
        )}
      </div>
    </div>
  );

  return (
    <aside className="flex h-full min-h-0 flex-col border-r border-rule bg-ground-2/40">
      <div className="shrink-0 px-4 py-4">
        <span className="font-display text-xl italic text-bone">Atelier</span>
        <p className="mt-1 text-[11px] leading-relaxed text-bone-muted">
          workspace copilot
        </p>
      </div>

      <ResizableSplit
        direction="vertical"
        defaultLeftPct={50}
        minLeftPct={15}
        maxLeftPct={85}
        left={threadsPanel}
        right={workspacePanel}
      />
    </aside>
  );
}

function TreeView({
  node,
  depth,
  onOpenFile,
}: {
  node: FileNode;
  depth: number;
  onOpenFile: (path: string) => void;
}) {
  if (depth === 0 && node.type === "dir") {
    return (
      <ul className="space-y-px">
        {(node.children ?? []).map((c) => (
          <TreeNode
            key={c.path || c.name}
            node={c}
            depth={1}
            onOpenFile={onOpenFile}
          />
        ))}
      </ul>
    );
  }
  return <TreeNode node={node} depth={depth} onOpenFile={onOpenFile} />;
}

function TreeNode({
  node,
  depth,
  onOpenFile,
}: {
  node: FileNode;
  depth: number;
  onOpenFile: (path: string) => void;
}) {
  const [open, setOpen] = useState(depth <= 1);
  const indent = (depth - 1) * 12;

  if (node.type === "dir") {
    return (
      <li>
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="flex w-full items-center gap-1.5 rounded px-2 py-1 text-left hover:bg-ground"
          style={{ paddingLeft: 8 + indent }}
        >
          <ChevronRight
            className={cn(
              "size-3 shrink-0 text-bone-muted transition-transform",
              open && "rotate-90"
            )}
            strokeWidth={1.6}
          />
          {open ? (
            <FolderOpen
              className="size-3.5 shrink-0 text-bone-dim"
              strokeWidth={1.6}
            />
          ) : (
            <Folder
              className="size-3.5 shrink-0 text-bone-dim"
              strokeWidth={1.6}
            />
          )}
          <span className="truncate text-[12.5px] text-bone-dim">
            {node.name}
          </span>
        </button>
        {open && (
          <ul>
            {(node.children ?? []).map((c) => (
              <TreeNode
                key={c.path || c.name}
                node={c}
                depth={depth + 1}
                onOpenFile={onOpenFile}
              />
            ))}
          </ul>
        )}
      </li>
    );
  }

  return (
    <li>
      <button
        type="button"
        onClick={() => onOpenFile(node.path)}
        className="group flex w-full items-center gap-1.5 rounded px-2 py-1 text-left hover:bg-ground"
        style={{ paddingLeft: 8 + indent + 14 }}
      >
        <FileText
          className="size-3 shrink-0 text-bone-muted group-hover:text-ember"
          strokeWidth={1.6}
        />
        <span className="truncate font-mono text-[11.5px] text-bone-dim group-hover:text-bone">
          {node.name}
        </span>
        {node.size !== undefined && (
          <span className="ml-auto pl-2 font-mono text-[10px] text-bone-muted">
            {formatSize(node.size)}
          </span>
        )}
      </button>
    </li>
  );
}

function formatSize(b: number) {
  if (b < 1024) return `${b}B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)}K`;
  return `${(b / (1024 * 1024)).toFixed(1)}M`;
}
