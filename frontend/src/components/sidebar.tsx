"use client";

import { useEffect, useState } from "react";
import {
  Folder,
  FolderOpen,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  FileText,
  File,
  BookOpen,
  HardDrive,
  Layers,
  RefreshCw,
  Plus,
  Trash2,
  X,
  BookMarked,
  Settings2,
  Wrench,
  FolderInput,
  Pencil,
} from "lucide-react";
import { cn } from "@/lib/cn";
import { workspaceImageUrl } from "@/lib/api";
import { useWorkspace } from "@/lib/workspace-store";
import { useChatStore } from "@/lib/chat-store";
import { useUIStore, type SidebarView } from "@/lib/ui-store";
import { fetchPageTree, fetchFileTree, fetchFile, uploadFile } from "@/lib/api";
import type { FileNode, PluginStatus } from "@/lib/types";
import type { ProjectKnowledgeLink } from "@/lib/api";
import { OutlookConnect, OUTLOOK_PLUGIN_ID } from "./outlook-connect";

const EMPTY_LINKS: ProjectKnowledgeLink[] = [];

export function Sidebar() {
  const sidebarView = useUIStore((s) => s.sidebarView);
  const toggleSidebarView = useUIStore((s) => s.toggleSidebarView);
  const collapseSidebar = useUIStore((s) => s.collapseSidebar);
  const expandSidebar = useUIStore((s) => s.expandSidebar);
  const setRightOpen = useUIStore((s) => s.setRightOpen);
  const openPromptModal = useUIStore((s) => s.openPromptModal);

  const pageTree = useWorkspace((s) => s.pageTree);
  const fileTree = useWorkspace((s) => s.fileTree);
  const setPageTree = useWorkspace((s) => s.setPageTree);
  const setFileTree = useWorkspace((s) => s.setFileTree);
  const setLoading = useWorkspace((s) => s.setTreeLoading);
  const loading = useWorkspace((s) => s.treeLoading);
  const openFile = useWorkspace((s) => s.openFile);
  const openImage = useWorkspace((s) => s.openImage);

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
  const plugins = useChatStore((s) => s.plugins);
  const togglePlugin = useChatStore((s) => s.togglePlugin);
  const toggleTool = useChatStore((s) => s.toggleTool);
  const systemPrompts = useChatStore((s) => s.systemPrompts);
  const activeSystemPromptId = useChatStore((s) => s.activeSystemPromptId);
  const selectSystemPrompt = useChatStore((s) => s.selectSystemPrompt);

  const [newProjectName, setNewProjectName] = useState("");
  const [showNewProject, setShowNewProject] = useState(false);

  const refresh = async () => {
    setLoading(true);
    try {
      const [pt, ft] = await Promise.all([fetchPageTree(), fetchFileTree()]);
      setPageTree(pt);
      setFileTree(ft);
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

  const IMAGE_EXTS = new Set(["png", "jpg", "jpeg", "gif", "webp", "svg"]);

  const handleOpenFile = async (path: string) => {
    const ext = path.split(".").pop()?.toLowerCase() ?? "";
    if (IMAGE_EXTS.has(ext)) {
      const url = workspaceImageUrl(path);
      openImage(path, url);
      setRightOpen(true);
      return;
    }
    try {
      const f = await fetchFile(path);
      openFile(f.path, f.content, f.kind);
      setRightOpen(true);
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
  const activeSystemPrompt = systemPrompts.find((p) => p.id === activeSystemPromptId);

  return (
    <aside className="flex h-full min-h-0 border-r border-rule bg-ground-2/40">
      {/* ── Icon rail ─────────────────────────────────────── */}
      <div className="flex w-10 shrink-0 flex-col items-center border-r border-rule/60 py-2 gap-1">
        {/* Collapse / expand toggle */}
        <button
          type="button"
          title={sidebarView !== null ? "collapse sidebar" : "expand sidebar"}
          aria-label={sidebarView !== null ? "collapse sidebar" : "expand sidebar"}
          onClick={sidebarView !== null ? collapseSidebar : expandSidebar}
          className="flex size-9 items-center justify-center rounded text-bone-muted hover:bg-ground hover:text-bone transition-colors"
        >
          {sidebarView !== null ? (
            <ChevronLeft className="size-4" strokeWidth={1.6} />
          ) : (
            <ChevronRight className="size-4" strokeWidth={1.6} />
          )}
        </button>

        <div className="my-0.5 w-5 border-t border-rule/50" />

        <RailIcon
          view="explorer"
          current={sidebarView}
          onToggle={toggleSidebarView}
          icon={Layers}
          label="Explorer"
        />
        <RailIcon
          view="settings"
          current={sidebarView}
          onToggle={toggleSidebarView}
          icon={Settings2}
          label="Settings"
        />
      </div>

      {/* ── Panel content ─────────────────────────────────── */}
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
        {sidebarView === "explorer" && (
          <ExplorerPanel
            ungrouped={ungrouped}
            projects={projects}
            conversations={conversations}
            activeConversationId={activeConversationId}
            isRunning={isRunning}
            newProjectName={newProjectName}
            showNewProject={showNewProject}
            onNewConversation={() => newConversation().catch(() => undefined)}
            onNewProject={() => setShowNewProject((v) => !v)}
            onProjectNameChange={setNewProjectName}
            onCreateProject={handleCreateProject}
            onCancelProject={() => { setShowNewProject(false); setNewProjectName(""); }}
            onSelect={(id) => selectConversation(id).catch(() => undefined)}
            onDelete={(id) => deleteConversation(id).catch(() => undefined)}
            onNewInProject={(pid) => newConversationInProject(pid).catch(() => undefined)}
            onDeleteProject={(pid) => deleteProject(pid).catch(() => undefined)}
            pageTree={pageTree}
            fileTree={fileTree}
            loading={loading}
            onOpenFile={handleOpenFile}
            onUpload={onUpload}
            onRefresh={refresh}
          />
        )}

        {sidebarView === "settings" && (
          <SettingsPanel
            models={models}
            activeModel={activeModel}
            onSelectModel={(m) => selectModel(m).catch(() => undefined)}
            plugins={plugins}
            onTogglePlugin={togglePlugin}
            onToggleTool={toggleTool}
            systemPrompts={systemPrompts}
            activeSystemPromptId={activeSystemPromptId}
            activeSystemPromptName={activeSystemPrompt?.name ?? null}
            onSelectPrompt={(id) => selectSystemPrompt(id).catch(() => undefined)}
            onOpenPromptModal={openPromptModal}
          />
        )}
      </div>
    </aside>
  );
}

/* ─── Rail icon ─────────────────────────────────────────────────────────── */

function RailIcon({
  view,
  current,
  onToggle,
  icon: Icon,
  label,
}: {
  view: Exclude<SidebarView, null>;
  current: SidebarView;
  onToggle: (v: Exclude<SidebarView, null>) => void;
  icon: React.ElementType;
  label: string;
}) {
  const active = current === view;
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      onClick={() => onToggle(view)}
      className={cn(
        "flex size-9 items-center justify-center rounded transition-colors",
        active
          ? "bg-ember-soft text-ember"
          : "text-bone-muted hover:bg-ground hover:text-bone"
      )}
    >
      <Icon className="size-4" strokeWidth={1.6} />
    </button>
  );
}

/* ─── Threads panel ─────────────────────────────────────────────────────── */

/* ─── Explorer panel (threads + files combined) ─────────────────────────── */

function ExplorerPanel({
  ungrouped, projects, conversations, activeConversationId, isRunning,
  newProjectName, showNewProject,
  onNewConversation, onNewProject, onProjectNameChange, onCreateProject, onCancelProject,
  onSelect, onDelete, onNewInProject, onDeleteProject,
  pageTree, fileTree, loading, onOpenFile, onUpload, onRefresh,
}: {
  ungrouped: { id: string; title: string }[];
  projects: { id: string; name: string; systemPromptId: string | null }[];
  conversations: { id: string; title: string; projectId: string | null }[];
  activeConversationId: string | null;
  isRunning: boolean;
  newProjectName: string;
  showNewProject: boolean;
  onNewConversation: () => void;
  onNewProject: () => void;
  onProjectNameChange: (v: string) => void;
  onCreateProject: () => void;
  onCancelProject: () => void;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
  onNewInProject: (pid: string) => void;
  onDeleteProject: (pid: string) => void;
  pageTree: FileNode | null;
  fileTree: FileNode | null;
  loading: boolean;
  onOpenFile: (path: string) => void;
  onUpload: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onRefresh: () => void;
}) {
  const [threadsOpen, setThreadsOpen] = useState(true);
  const [filesOpen, setFilesOpen] = useState(true);

  return (
    <div className="flex h-full min-h-0 flex-col overflow-y-auto">
      {/* ── Threads section ── */}
      <div className="shrink-0">
        <div className="flex items-center gap-1 px-2 py-1.5">
          <button
            type="button"
            onClick={() => setThreadsOpen((o) => !o)}
            className="flex min-w-0 flex-1 items-center gap-1 text-left"
          >
            <ChevronDown
              className={cn("size-3 shrink-0 text-bone-muted transition-transform", !threadsOpen && "-rotate-90")}
              strokeWidth={1.6}
            />
            <span className="smallcaps">threads</span>
          </button>
          <button type="button" aria-label="new chat" title="new chat" disabled={isRunning}
            onClick={(e) => { e.stopPropagation(); onNewConversation(); }}
            className="rounded p-1 text-bone-muted hover:bg-ground hover:text-bone disabled:opacity-40">
            <Plus className="size-3" strokeWidth={1.6} />
          </button>
          <button type="button" aria-label="new project" title="new project" disabled={isRunning}
            onClick={(e) => { e.stopPropagation(); onNewProject(); }}
            className="rounded p-1 text-bone-muted hover:bg-ground hover:text-bone disabled:opacity-40">
            <Folder className="size-3" strokeWidth={1.6} />
          </button>
        </div>

        {threadsOpen && (
          <div className="px-2 pb-1">
            {showNewProject && (
              <div className="mb-1.5 flex items-center gap-1">
                <input autoFocus type="text" placeholder="project name" value={newProjectName}
                  onChange={(e) => onProjectNameChange(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") onCreateProject(); if (e.key === "Escape") onCancelProject(); }}
                  className="min-w-0 flex-1 rounded border border-rule bg-ground px-2 py-0.5 text-[11.5px] text-bone outline-none placeholder:text-bone-muted"
                />
                <button type="button" onClick={onCreateProject} className="rounded p-1 text-bone-muted hover:bg-ground hover:text-bone"><Plus className="size-3" strokeWidth={1.6} /></button>
                <button type="button" onClick={onCancelProject} className="rounded p-1 text-bone-muted hover:bg-ground hover:text-bone"><X className="size-3" strokeWidth={1.6} /></button>
              </div>
            )}
            <ul className="space-y-0.5">
              {ungrouped.map((c) => (
                <ConversationItem key={c.id} id={c.id} title={c.title}
                  active={c.id === activeConversationId} isRunning={isRunning}
                  onSelect={() => onSelect(c.id)} onDelete={() => onDelete(c.id)} />
              ))}
              {projects.map((project) => {
                const projectConvs = conversations.filter((c) => c.projectId === project.id);
                return (
                  <ProjectFolder key={project.id} project={project} conversations={projectConvs}
                    activeConversationId={activeConversationId} isRunning={isRunning}
                    onSelect={onSelect} onDelete={onDelete}
                    onNewConversation={() => onNewInProject(project.id)}
                    onDeleteProject={() => onDeleteProject(project.id)} />
                );
              })}
              {conversations.length === 0 && (
                <li className="px-2.5 py-1 text-[11.5px] text-bone-muted">no chats yet</li>
              )}
            </ul>
          </div>
        )}
      </div>

      <div className="mx-3 border-t border-rule/60" />

      {/* ── Files section ── */}
      <div className="shrink-0">
        <div className="flex items-center gap-1 px-2 py-1.5">
          <button
            type="button"
            onClick={() => setFilesOpen((o) => !o)}
            className="flex min-w-0 flex-1 items-center gap-1 text-left"
          >
            <ChevronDown
              className={cn("size-3 shrink-0 text-bone-muted transition-transform", !filesOpen && "-rotate-90")}
              strokeWidth={1.6}
            />
            <span className="smallcaps">files</span>
          </button>
          <label className="cursor-pointer rounded p-1 text-bone-muted hover:bg-ground hover:text-bone" aria-label="upload" title="upload file">
            <Plus className="size-3" strokeWidth={1.6} />
            <input type="file" className="hidden" onChange={onUpload} />
          </label>
          <button type="button" aria-label="refresh" title="refresh" onClick={onRefresh}
            className="rounded p-1 text-bone-muted hover:bg-ground hover:text-bone">
            <RefreshCw className={cn("size-3", loading && "animate-spin text-ember")} strokeWidth={1.6} />
          </button>
        </div>

        {filesOpen && (
          <div className="px-2 pb-4">
            <div className="mb-1 flex items-center gap-1.5 px-2 pt-0.5 pb-0.5">
              <BookOpen className="size-3 text-ember/70" strokeWidth={1.6} />
              <span className="text-[10px] uppercase tracking-widest text-ember/70">Workspace</span>
            </div>
            {pageTree ? (
              <TreeView node={pageTree} depth={0} onOpenFile={onOpenFile} variant="pages" />
            ) : (
              <p className="px-3 py-1 text-[11px] text-bone-muted">loading…</p>
            )}

            <div className="mx-2 my-2 border-t border-rule/60" />

            <div className="mb-1 flex items-center gap-1.5 px-2 pb-0.5">
              <HardDrive className="size-3 text-sky-400/70" strokeWidth={1.6} />
              <span className="text-[10px] uppercase tracking-widest text-sky-400/70">Filesystem</span>
            </div>
            {fileTree ? (
              <TreeView node={fileTree} depth={0} onOpenFile={onOpenFile} variant="files" />
            ) : (
              <p className="px-3 py-1 text-[11px] text-bone-muted">loading…</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

/* ─── Settings panel ────────────────────────────────────────────────────── */

function SettingsPanel({
  models,
  activeModel,
  onSelectModel,
  plugins,
  onTogglePlugin,
  onToggleTool,
  systemPrompts,
  activeSystemPromptId,
  activeSystemPromptName,
  onSelectPrompt,
  onOpenPromptModal,
}: {
  models: { id: string; name: string; model: string }[];
  activeModel: string | null;
  onSelectModel: (m: string) => void;
  plugins: PluginStatus[];
  onTogglePlugin: (id: string, enabled: boolean) => void;
  onToggleTool: (pluginId: string, toolName: string, enabled: boolean) => void;
  systemPrompts: { id: string; name: string }[];
  activeSystemPromptId: string | null;
  activeSystemPromptName: string | null;
  onSelectPrompt: (id: string) => void;
  onOpenPromptModal: () => void;
}) {
  const [pluginsOpen, setPluginsOpen] = useState(true);
  const [promptsOpen, setPromptsOpen] = useState(true);
  const [expandedPlugins, setExpandedPlugins] = useState<Set<string>>(new Set());

  const togglePluginExpanded = (id: string) => {
    setExpandedPlugins((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <div className="flex h-full flex-col overflow-y-auto">
      <div className="py-2">
        {/* Model */}
        {models.length > 0 && (
          <div className="px-4 pb-3 pt-2">
            <span className="smallcaps block mb-2">model</span>
            <select
              value={activeModel ?? ""}
              onChange={(e) => onSelectModel(e.target.value)}
              className="w-full rounded border border-rule bg-ground px-2 py-1.5 text-[11.5px] text-bone-dim outline-none hover:border-bone-muted focus:border-bone-muted"
            >
              {models.map((m) => (
                <option key={m.model} value={m.model}>{m.name}</option>
              ))}
            </select>
          </div>
        )}

        <div className="mx-3 border-t border-rule/60" />

        {/* Plugins — collapsible section */}
        <div>
          <button
            type="button"
            onClick={() => setPluginsOpen((o) => !o)}
            className="flex w-full items-center gap-1 px-3 py-2 text-left"
          >
            <ChevronDown
              className={cn("size-3 shrink-0 text-bone-muted transition-transform", !pluginsOpen && "-rotate-90")}
              strokeWidth={1.6}
            />
            <span className="smallcaps flex-1">plugins</span>
            <span className="font-mono text-[9.5px] text-bone-muted">
              {plugins.filter((p) => p.enabled).length}/{plugins.length}
            </span>
          </button>

          {pluginsOpen && (
            <div className="space-y-px px-2 pb-2">
              {plugins.map((plugin) => {
                const expanded = expandedPlugins.has(plugin.id);
                return (
                  <div
                    key={plugin.id}
                    className={cn(
                      "rounded border transition-colors",
                      plugin.enabled
                        ? "border-ember/25 bg-ember-soft/5"
                        : "border-rule/60 bg-ground/30"
                    )}
                  >
                    {/* Collapsed row — always visible */}
                    <div className="flex items-center gap-1.5 px-2 py-1.5">
                      <button
                        type="button"
                        onClick={() => togglePluginExpanded(plugin.id)}
                        className="flex min-w-0 flex-1 items-center gap-1.5"
                      >
                        <ChevronRight
                          className={cn(
                            "size-3 shrink-0 text-bone-muted transition-transform",
                            expanded && "rotate-90"
                          )}
                          strokeWidth={1.6}
                        />
                        <span className={cn(
                          "size-1.5 shrink-0 rounded-full",
                          plugin.enabled ? "bg-ember" : "bg-bone-muted/40"
                        )} />
                        <span className={cn(
                          "min-w-0 flex-1 truncate text-left text-[12px] font-medium",
                          plugin.enabled ? "text-bone" : "text-bone-muted"
                        )}>
                          {plugin.name}
                        </span>
                        {plugin.type === "core" && (
                          <span className="shrink-0 rounded border border-rule/60 px-1 py-px font-mono text-[9px] text-bone-muted/60">
                            core
                          </span>
                        )}
                        {plugin.isMcp && (
                          <span className="shrink-0 rounded border border-rule/60 px-1 py-px font-mono text-[9px] text-bone-muted/60">
                            mcp
                          </span>
                        )}
                        {plugin.isMcp && plugin.mcpConfigured === false && (
                          <span
                            title="MCP server URL/token not configured — set the env vars to enable"
                            className="shrink-0 rounded border border-amber-500/40 px-1 py-px font-mono text-[9px] text-amber-500/80"
                          >
                            setup
                          </span>
                        )}
                      </button>
                      <button
                        type="button"
                        onClick={() => onTogglePlugin(plugin.id, !plugin.enabled)}
                        className={cn(
                          "shrink-0 rounded border px-2 py-0.5 font-mono text-[10px] transition-colors",
                          plugin.enabled
                            ? "border-ember/40 text-ember hover:bg-ember-soft/30"
                            : "border-rule text-bone-muted hover:border-rule-strong hover:text-bone"
                        )}
                      >
                        {plugin.enabled ? "on" : "off"}
                      </button>
                    </div>

                    {/* Expanded: description + tool chips */}
                    {expanded && (
                      <div className="border-t border-rule/40 px-3 pb-2.5 pt-2">
                        {plugin.description && (
                          <p className="mb-2 text-[11px] leading-snug text-bone-muted">
                            {plugin.description}
                          </p>
                        )}
                        {plugin.isMcp && plugin.mcpConfigured === false && (
                          <p className="mb-2 text-[11px] leading-snug text-amber-500/80">
                            Not configured yet — set this server&apos;s URL and
                            token environment variables, then restart the backend.
                          </p>
                        )}
                        {plugin.tools.length > 0 && (
                          <div className="flex flex-wrap gap-1">
                            {plugin.tools.map((t) => {
                              const toolEnabled = plugin.toolsEnabled?.[t] ?? true;
                              return (
                                <button
                                  key={t}
                                  type="button"
                                  title={toolEnabled ? `disable ${t}` : `enable ${t}`}
                                  disabled={!plugin.enabled}
                                  onClick={() => onToggleTool(plugin.id, t, !toolEnabled)}
                                  className={cn(
                                    "inline-flex items-center gap-0.5 rounded border px-1 py-px font-mono text-[9.5px] transition-colors",
                                    !plugin.enabled
                                      ? "cursor-not-allowed border-rule/40 bg-ground-2/30 text-bone-muted/50 opacity-50"
                                      : toolEnabled
                                      ? "border-ember/40 bg-ember-soft/20 text-ember hover:bg-ember-soft/40"
                                      : "border-rule bg-ground-2/40 text-bone-muted line-through hover:border-rule-strong hover:text-bone-dim"
                                  )}
                                >
                                  <Wrench className="size-2" strokeWidth={1.5} />
                                  {t}
                                </button>
                              );
                            })}
                          </div>
                        )}
                        {plugin.id === OUTLOOK_PLUGIN_ID && <OutlookConnect />}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <div className="mx-3 border-t border-rule/60" />

        {/* System prompts — collapsible section */}
        {systemPrompts.length > 0 && (
          <div>
            <div className="flex items-center gap-1 px-3 py-2">
              <button
                type="button"
                onClick={() => setPromptsOpen((o) => !o)}
                className="flex min-w-0 flex-1 items-center gap-1 text-left"
              >
                <ChevronDown
                  className={cn("size-3 shrink-0 text-bone-muted transition-transform", !promptsOpen && "-rotate-90")}
                  strokeWidth={1.6}
                />
                <span className="smallcaps flex-1">system prompt</span>
              </button>
              <button
                type="button"
                onClick={onOpenPromptModal}
                className="rounded border border-rule px-2 py-0.5 font-mono text-[10px] text-bone-muted hover:bg-ground-2 hover:text-bone"
              >
                manage
              </button>
            </div>

            {promptsOpen && (
              <div className="px-2 pb-3">
                <div className="space-y-px rounded border border-rule/60 bg-ground/40 p-1">
                  {systemPrompts.map((p) => {
                    const active = p.id === activeSystemPromptId;
                    return (
                      <button
                        key={p.id}
                        type="button"
                        onClick={() => onSelectPrompt(p.id)}
                        className={cn(
                          "flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-[11.5px] transition-colors",
                          active
                            ? "bg-ember-soft text-bone"
                            : "text-bone-dim hover:bg-ground-2 hover:text-bone"
                        )}
                      >
                        <span className={cn(
                          "size-1.5 shrink-0 rounded-full",
                          active ? "bg-ember" : "border border-bone-muted bg-transparent"
                        )} />
                        <span className="min-w-0 flex-1 truncate">{p.name}</span>
                      </button>
                    );
                  })}
                </div>
                {activeSystemPromptName && (
                  <p className="mt-1.5 px-1 font-mono text-[10px] text-bone-muted">
                    active: <span className="text-bone">{activeSystemPromptName}</span>
                  </p>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

/* ─── Conversation item ─────────────────────────────────────────────────── */

function ConversationItem({
  id,
  title,
  active,
  isRunning,
  projectId = null,
  onSelect,
  onDelete,
  indent = false,
}: {
  id: string;
  title: string;
  active: boolean;
  isRunning: boolean;
  projectId?: string | null;
  onSelect: () => void;
  onDelete: () => void;
  indent?: boolean;
}) {
  const [hovered, setHovered] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const projects = useChatStore((s) => s.projects);
  const moveConversation = useChatStore((s) => s.moveConversation);

  const targets = projects.filter((p) => p.id !== projectId);
  const canMove = targets.length > 0 || projectId !== null;

  const move = (target: string | null) => {
    setMenuOpen(false);
    moveConversation(id, target).catch(() => undefined);
  };

  return (
    <li
      className="relative"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => { setHovered(false); setMenuOpen(false); }}
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
          <span className={cn("size-1.5 shrink-0 rounded-full", active ? "bg-ember" : "bg-bone-muted")} />
          <span className="min-w-0 flex-1 truncate text-left text-[12px]">{title}</span>
        </button>
        {(hovered || menuOpen) && (
          <>
            {canMove && (
              <button
                type="button"
                title="move to folder"
                onClick={(e) => { e.stopPropagation(); setMenuOpen((o) => !o); }}
                className="shrink-0 rounded p-0.5 text-bone-muted hover:text-bone"
              >
                <FolderInput className="size-3" strokeWidth={1.6} />
              </button>
            )}
            <button
              type="button"
              title="delete conversation"
              onClick={(e) => { e.stopPropagation(); onDelete(); }}
              className="shrink-0 rounded p-0.5 text-bone-muted hover:text-red-400"
            >
              <Trash2 className="size-3" strokeWidth={1.6} />
            </button>
          </>
        )}
      </div>
      {menuOpen && (
        <div className="absolute right-1 top-full z-20 mt-0.5 min-w-[140px] max-w-[200px] rounded border border-rule bg-ground shadow-lg">
          <p className="border-b border-rule/60 px-2 py-1 text-[10px] uppercase tracking-widest text-bone-muted">move to</p>
          <ul className="max-h-48 overflow-y-auto py-0.5">
            {projectId !== null && (
              <li>
                <button
                  type="button"
                  onClick={() => move(null)}
                  className="flex w-full items-center gap-1.5 px-2 py-1 text-left text-[11.5px] text-bone-dim hover:bg-ground-2/60 hover:text-bone"
                >
                  <X className="size-3 shrink-0" strokeWidth={1.6} />
                  No folder
                </button>
              </li>
            )}
            {targets.map((p) => (
              <li key={p.id}>
                <button
                  type="button"
                  onClick={() => move(p.id)}
                  className="flex w-full items-center gap-1.5 px-2 py-1 text-left text-[11.5px] text-bone-dim hover:bg-ground-2/60 hover:text-bone"
                >
                  <Folder className="size-3 shrink-0 text-bone-muted" strokeWidth={1.6} />
                  <span className="truncate">{p.name}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </li>
  );
}

/* ─── Project folder ────────────────────────────────────────────────────── */

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
  const [renaming, setRenaming] = useState(false);
  const [nameDraft, setNameDraft] = useState(project.name);

  const links = useChatStore((s) => s.projectKnowledge[project.id]) ?? EMPTY_LINKS;
  const activeProjectId = useChatStore((s) => s.activeProjectId);
  const selectProject = useChatStore((s) => s.selectProject);
  const renameProject = useChatStore((s) => s.renameProject);
  const loadKnowledge = useChatStore((s) => s.loadProjectKnowledge);
  const removeKnowledge = useChatStore((s) => s.removeProjectKnowledge);
  const openPicker = useUIStore((s) => s.openKnowledgePicker);

  const isActive = activeProjectId === project.id;

  const submitRename = () => {
    const next = nameDraft.trim();
    setRenaming(false);
    if (next && next !== project.name) {
      renameProject(project.id, next).catch(() => undefined);
    }
  };

  useEffect(() => {
    loadKnowledge(project.id).catch(() => undefined);
  }, [project.id, loadKnowledge]);

  return (
    <li>
      <div
        className={cn(
          "flex w-full items-center gap-1 rounded px-1 py-1 hover:bg-ground/50",
          isActive && "bg-ember-soft/40"
        )}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
      >
        <button
          type="button"
          aria-label={open ? "collapse" : "expand"}
          onClick={() => setOpen((o) => !o)}
          className="flex size-4 shrink-0 items-center justify-center text-bone-muted hover:text-bone"
        >
          <ChevronRight className={cn("size-3 transition-transform", open && "rotate-90")} strokeWidth={1.6} />
        </button>
        {renaming ? (
          <div className="flex min-w-0 flex-1 items-center gap-1.5">
            {open ? (
              <FolderOpen className="size-3.5 shrink-0 text-bone-dim" strokeWidth={1.6} />
            ) : (
              <Folder className="size-3.5 shrink-0 text-bone-dim" strokeWidth={1.6} />
            )}
            <input
              autoFocus
              type="text"
              value={nameDraft}
              onChange={(e) => setNameDraft(e.target.value)}
              onBlur={submitRename}
              onKeyDown={(e) => {
                if (e.key === "Enter") submitRename();
                if (e.key === "Escape") { setNameDraft(project.name); setRenaming(false); }
              }}
              className="min-w-0 flex-1 rounded border border-rule bg-ground px-1.5 py-0.5 text-[12px] text-bone outline-none"
            />
          </div>
        ) : (
          <button
            type="button"
            onClick={() => selectProject(project.id)}
            onDoubleClick={() => { setNameDraft(project.name); setRenaming(true); }}
            className="flex min-w-0 flex-1 items-center gap-1.5"
          >
            {open ? (
              <FolderOpen className="size-3.5 shrink-0 text-bone-dim" strokeWidth={1.6} />
            ) : (
              <Folder className="size-3.5 shrink-0 text-bone-dim" strokeWidth={1.6} />
            )}
            <span
              className={cn(
                "min-w-0 flex-1 truncate text-left text-[12px]",
                isActive ? "text-ember" : "text-bone-dim"
              )}
            >
              {project.name}
            </span>
            {links.length > 0 && (
              <span
                title={`${links.length} knowledge link${links.length === 1 ? "" : "s"}`}
                className="shrink-0 rounded bg-ember-soft px-1 font-mono text-[10px] text-ember"
              >
                {links.length}
              </span>
            )}
          </button>
        )}
        {hovered && !renaming && (
          <>
            <button type="button" title="rename project" onClick={() => { setNameDraft(project.name); setRenaming(true); }} className="shrink-0 rounded p-0.5 text-bone-muted hover:text-bone">
              <Pencil className="size-3" strokeWidth={1.6} />
            </button>
            <button type="button" title="manage knowledge" onClick={() => openPicker(project.id)} className="shrink-0 rounded p-0.5 text-bone-muted hover:text-bone">
              <BookMarked className="size-3" strokeWidth={1.6} />
            </button>
            <button type="button" title="new chat in project" disabled={isRunning} onClick={onNewConversation} className="shrink-0 rounded p-0.5 text-bone-muted hover:text-bone disabled:opacity-40">
              <Plus className="size-3" strokeWidth={1.6} />
            </button>
            <button type="button" title="delete project" onClick={onDeleteProject} className="shrink-0 rounded p-0.5 text-bone-muted hover:text-red-400">
              <Trash2 className="size-3" strokeWidth={1.6} />
            </button>
          </>
        )}
      </div>
      {open && (
        <>
          {links.length > 0 && (
            <ul className="ml-5 mb-1 flex flex-wrap gap-1">
              {links.map((link) => {
                const label = link.ref_path.split("/").slice(-2).join("/");
                const isFolder = link.ref_type === "page_folder";
                return (
                  <li key={link.id}>
                    <span
                      title={`${link.ref_type}: ${link.ref_path}`}
                      className="group inline-flex items-center gap-1 rounded border border-rule bg-ground/40 px-1.5 py-0.5 font-mono text-[10px] text-bone-dim"
                    >
                      {isFolder ? (
                        <Folder className="size-2.5 text-ember" strokeWidth={1.6} />
                      ) : (
                        <FileText className="size-2.5 text-bone-muted" strokeWidth={1.6} />
                      )}
                      <span className="truncate max-w-[140px]">{label}</span>
                      <button
                        type="button"
                        aria-label="unpin"
                        onClick={() => removeKnowledge(project.id, link.id).catch(() => undefined)}
                        className="text-bone-muted hover:text-red-400 opacity-0 group-hover:opacity-100"
                      >
                        <X className="size-2.5" strokeWidth={1.8} />
                      </button>
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
          <ul className="ml-2 space-y-0.5 border-l border-rule/50 pl-1">
            {conversations.map((c) => (
              <ConversationItem
                key={c.id}
                id={c.id}
                title={c.title}
                active={c.id === activeConversationId}
                isRunning={isRunning}
                projectId={project.id}
                onSelect={() => onSelect(c.id)}
                onDelete={() => onDelete(c.id)}
                indent
              />
            ))}
            {conversations.length === 0 && (
              <li className="px-4 py-1 text-[11px] text-bone-muted">empty</li>
            )}
          </ul>
        </>
      )}
    </li>
  );
}

/* ─── Tree view ─────────────────────────────────────────────────────────── */

type TreeVariant = "pages" | "files";

function TreeView({ node, depth, onOpenFile, variant = "pages" }: {
  node: FileNode; depth: number; onOpenFile: (path: string) => void; variant?: TreeVariant;
}) {
  if (depth === 0 && node.type === "dir") {
    return (
      <ul className="space-y-px">
        {(node.children ?? []).map((c) => (
          <TreeNode key={c.path || c.name} node={c} depth={1} onOpenFile={onOpenFile} variant={variant} />
        ))}
      </ul>
    );
  }
  return <TreeNode node={node} depth={depth} onOpenFile={onOpenFile} variant={variant} />;
}

function TreeNode({ node, depth, onOpenFile, variant }: {
  node: FileNode; depth: number; onOpenFile: (path: string) => void; variant: TreeVariant;
}) {
  const [open, setOpen] = useState(false);
  const indent = (depth - 1) * 12;
  const fileIconClass = variant === "pages"
    ? "size-3 shrink-0 text-ember/50 group-hover:text-ember"
    : "size-3 shrink-0 text-sky-400/50 group-hover:text-sky-400";
  const FileIcon = variant === "pages" ? FileText : File;

  if (node.type === "dir") {
    return (
      <li>
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="flex w-full items-center gap-1.5 rounded px-2 py-1 text-left hover:bg-ground"
          style={{ paddingLeft: 8 + indent }}
        >
          <ChevronRight className={cn("size-3 shrink-0 text-bone-muted transition-transform", open && "rotate-90")} strokeWidth={1.6} />
          {open ? <FolderOpen className="size-3.5 shrink-0 text-bone-dim" strokeWidth={1.6} /> : <Folder className="size-3.5 shrink-0 text-bone-dim" strokeWidth={1.6} />}
          <span className="truncate text-[12.5px] text-bone-dim">{node.name}</span>
        </button>
        {open && (
          <ul>
            {(node.children ?? []).map((c) => (
              <TreeNode key={c.path || c.name} node={c} depth={depth + 1} onOpenFile={onOpenFile} variant={variant} />
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
        <FileIcon className={fileIconClass} strokeWidth={1.6} />
        <span className="truncate font-mono text-[11.5px] text-bone-dim group-hover:text-bone">{node.name}</span>
        {node.size !== undefined && (
          <span className="ml-auto pl-2 font-mono text-[10px] text-bone-muted">{formatSize(node.size)}</span>
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
