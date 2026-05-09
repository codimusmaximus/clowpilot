"use client";

import { useEffect, useState } from "react";
import {
  Folder,
  FolderOpen,
  ChevronRight,
  FileText,
  RefreshCw,
  Plus,
  Trash2,
  X,
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
  const newConversationInProject = useChatStore((s) => s.newConversationInProject);
  const deleteConversation = useChatStore((s) => s.deleteConversation);
  const selectConversation = useChatStore((s) => s.selectConversation);
  const projects = useChatStore((s) => s.projects);
  const createProject = useChatStore((s) => s.createProject);
  const deleteProject = useChatStore((s) => s.deleteProject);
  const models = useChatStore((s) => s.models);
  const activeModel = useChatStore((s) => s.activeModel);
  const selectModel = useChatStore((s) => s.selectModel);

  const [newProjectName, setNewProjectName] = useState("");
  const [showNewProject, setShowNewProject] = useState(false);

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

  const handleCreateProject = async () => {
    const name = newProjectName.trim();
    if (!name) return;
    await createProject(name).catch(() => undefined);
    setNewProjectName("");
    setShowNewProject(false);
  };

  const ungrouped = conversations.filter((c) => !c.projectId);

  const threadsPanel = (
    <div className="flex h-full flex-col px-4 pt-3 pb-1">
      <div className="flex items-center gap-1 shrink-0">
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
        <button
          type="button"
          aria-label="new project"
          title="new project"
          disabled={isRunning}
          onClick={() => setShowNewProject((v) => !v)}
          className="rounded p-1 text-bone-muted hover:bg-ground hover:text-bone disabled:opacity-40"
        >
          <Folder className="size-3" strokeWidth={1.6} />
        </button>
      </div>

      {showNewProject && (
        <div className="mt-1.5 flex items-center gap-1">
          <input
            autoFocus
            type="text"
            placeholder="project name"
            value={newProjectName}
            onChange={(e) => setNewProjectName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleCreateProject();
              if (e.key === "Escape") { setShowNewProject(false); setNewProjectName(""); }
            }}
            className="min-w-0 flex-1 rounded border border-rule bg-ground px-2 py-0.5 text-[11.5px] text-bone outline-none placeholder:text-bone-muted"
          />
          <button
            type="button"
            onClick={handleCreateProject}
            className="rounded p-1 text-bone-muted hover:bg-ground hover:text-bone"
          >
            <Plus className="size-3" strokeWidth={1.6} />
          </button>
          <button
            type="button"
            onClick={() => { setShowNewProject(false); setNewProjectName(""); }}
            className="rounded p-1 text-bone-muted hover:bg-ground hover:text-bone"
          >
            <X className="size-3" strokeWidth={1.6} />
          </button>
        </div>
      )}

      <ul className="mt-1.5 min-h-0 flex-1 space-y-0.5 overflow-y-auto">
        {ungrouped.map((conversation) => (
          <ConversationItem
            key={conversation.id}
            id={conversation.id}
            title={conversation.title}
            active={conversation.id === activeConversationId}
            isRunning={isRunning}
            onSelect={() => selectConversation(conversation.id).catch(() => undefined)}
            onDelete={() => deleteConversation(conversation.id).catch(() => undefined)}
          />
        ))}

        {projects.map((project) => {
          const projectConvs = conversations.filter((c) => c.projectId === project.id);
          return (
            <ProjectFolder
              key={project.id}
              project={project}
              conversations={projectConvs}
              activeConversationId={activeConversationId}
              isRunning={isRunning}
              onSelect={(id) => selectConversation(id).catch(() => undefined)}
              onDelete={(id) => deleteConversation(id).catch(() => undefined)}
              onNewConversation={() => newConversationInProject(project.id).catch(() => undefined)}
              onDeleteProject={() => deleteProject(project.id).catch(() => undefined)}
            />
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
        {models.length > 0 && (
          <ModelSelector
            models={models}
            activeModel={activeModel}
            onSelect={(m) => selectModel(m).catch(() => undefined)}
          />
        )}
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

function ConversationItem({
  id,
  title,
  active,
  isRunning,
  onSelect,
  onDelete,
  indent = false,
}: {
  id: string;
  title: string;
  active: boolean;
  isRunning: boolean;
  onSelect: () => void;
  onDelete: () => void;
  indent?: boolean;
}) {
  const [hovered, setHovered] = useState(false);
  return (
    <li
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <div
        className={cn(
          "group flex w-full items-center gap-2 rounded border px-2.5 py-1.5",
          indent && "pl-5",
          active
            ? "border-rule bg-ground/60 text-bone"
            : "border-transparent text-bone-dim hover:bg-ground/50 hover:text-bone"
        )}
      >
        <button
          type="button"
          disabled={isRunning}
          onClick={onSelect}
          className="flex min-w-0 flex-1 items-center gap-2 disabled:opacity-40"
        >
          <span
            className={cn(
              "size-1.5 shrink-0 rounded-full",
              active ? "bg-ember" : "bg-bone-muted"
            )}
          />
          <span className="min-w-0 flex-1 truncate text-left text-[12px]">
            {title}
          </span>
        </button>
        {hovered && (
          <button
            type="button"
            title="delete conversation"
            onClick={(e) => { e.stopPropagation(); onDelete(); }}
            className="shrink-0 rounded p-0.5 text-bone-muted hover:text-red-400"
          >
            <Trash2 className="size-3" strokeWidth={1.6} />
          </button>
        )}
      </div>
    </li>
  );
}

function ProjectFolder({
  project,
  conversations,
  activeConversationId,
  isRunning,
  onSelect,
  onDelete,
  onNewConversation,
  onDeleteProject,
}: {
  project: { id: string; name: string; systemPromptId: string | null };
  conversations: { id: string; title: string }[];
  activeConversationId: string | null;
  isRunning: boolean;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
  onNewConversation: () => void;
  onDeleteProject: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [hovered, setHovered] = useState(false);

  return (
    <li>
      <div
        className="flex w-full items-center gap-1 rounded px-1 py-1 hover:bg-ground/50"
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
      >
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="flex min-w-0 flex-1 items-center gap-1.5"
        >
          <ChevronRight
            className={cn(
              "size-3 shrink-0 text-bone-muted transition-transform",
              open && "rotate-90"
            )}
            strokeWidth={1.6}
          />
          {open ? (
            <FolderOpen className="size-3.5 shrink-0 text-bone-dim" strokeWidth={1.6} />
          ) : (
            <Folder className="size-3.5 shrink-0 text-bone-dim" strokeWidth={1.6} />
          )}
          <span className="min-w-0 flex-1 truncate text-left text-[12px] text-bone-dim">
            {project.name}
          </span>
        </button>
        {hovered && (
          <>
            <button
              type="button"
              title="new chat in project"
              disabled={isRunning}
              onClick={onNewConversation}
              className="shrink-0 rounded p-0.5 text-bone-muted hover:text-bone disabled:opacity-40"
            >
              <Plus className="size-3" strokeWidth={1.6} />
            </button>
            <button
              type="button"
              title="delete project"
              onClick={onDeleteProject}
              className="shrink-0 rounded p-0.5 text-bone-muted hover:text-red-400"
            >
              <Trash2 className="size-3" strokeWidth={1.6} />
            </button>
          </>
        )}
      </div>
      {open && (
        <ul className="ml-2 space-y-0.5 border-l border-rule/50 pl-1">
          {conversations.map((c) => (
            <ConversationItem
              key={c.id}
              id={c.id}
              title={c.title}
              active={c.id === activeConversationId}
              isRunning={isRunning}
              onSelect={() => onSelect(c.id)}
              onDelete={() => onDelete(c.id)}
              indent
            />
          ))}
          {conversations.length === 0 && (
            <li className="px-4 py-1 text-[11px] text-bone-muted">empty</li>
          )}
        </ul>
      )}
    </li>
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
  const [open, setOpen] = useState(false);
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

function ModelSelector({
  models,
  activeModel,
  onSelect,
}: {
  models: { id: string; name: string; model: string }[];
  activeModel: string | null;
  onSelect: (model: string) => void;
}) {
  const active = models.find((m) => m.model === activeModel) ?? models[0];
  return (
    <div className="mt-2">
      <select
        value={active?.model ?? ""}
        onChange={(e) => onSelect(e.target.value)}
        className="w-full rounded border border-rule bg-ground px-2 py-1 text-[11px] text-bone-dim outline-none hover:border-bone-muted focus:border-bone-muted"
        title="Active LLM"
      >
        {models.map((m) => (
          <option key={m.model} value={m.model}>
            {m.name}
          </option>
        ))}
      </select>
    </div>
  );
}

function formatSize(b: number) {
  if (b < 1024) return `${b}B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)}K`;
  return `${(b / (1024 * 1024)).toFixed(1)}M`;
}
