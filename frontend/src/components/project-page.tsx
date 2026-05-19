"use client";

import { useEffect, useState } from "react";
import { BookMarked, FileText, Folder, Plus, Sliders, X } from "lucide-react";
import { useChatStore } from "@/lib/chat-store";
import { useUIStore } from "@/lib/ui-store";
import { cn } from "@/lib/cn";
import type { ProjectKnowledgeLink } from "@/lib/api";
import type { KnowledgeMode, Project } from "@/lib/types";

const EMPTY_LINKS: ProjectKnowledgeLink[] = [];

export function ProjectPage() {
  const activeProjectId = useChatStore((s) => s.activeProjectId);
  const project = useChatStore((s) =>
    s.projects.find((p) => p.id === s.activeProjectId)
  );

  if (!activeProjectId || !project) return null;

  return <ProjectPageContent project={project} />;
}

function ProjectPageContent({ project }: { project: Project }) {
  const projectId = project.id;
  const links =
    useChatStore((s) => s.projectKnowledge[projectId]) ?? EMPTY_LINKS;
  const loadKnowledge = useChatStore((s) => s.loadProjectKnowledge);
  const removeKnowledge = useChatStore((s) => s.removeProjectKnowledge);
  const setSettings = useChatStore((s) => s.setProjectKnowledgeSettings);
  const selectProject = useChatStore((s) => s.selectProject);
  const openPicker = useUIStore((s) => s.openKnowledgePicker);

  const [draftPreview, setDraftPreview] = useState(project.knowledgePreviewTokens);
  useEffect(() => {
    setDraftPreview(project.knowledgePreviewTokens);
  }, [project.knowledgePreviewTokens]);

  useEffect(() => {
    loadKnowledge(projectId).catch(() => undefined);
  }, [projectId, loadKnowledge]);

  const setMode = (mode: KnowledgeMode) => {
    setSettings(projectId, mode, project.knowledgePreviewTokens).catch(() => undefined);
  };
  const commitPreviewTokens = () => {
    const n = Math.max(50, Math.min(5000, draftPreview || 500));
    if (n !== project.knowledgePreviewTokens) {
      setSettings(projectId, project.knowledgeMode, n).catch(() => undefined);
    }
  };

  return (
    <div className="flex h-full w-full min-h-0 flex-col bg-ground">
      <header className="shrink-0 border-b border-rule flex items-center gap-3 px-6 py-3.5">
        <span className="size-1.5 rounded-full bg-ember" />
        <span className="smallcaps">project</span>
        <span className="font-display text-base italic text-bone">
          {project.name}
        </span>
        <span className="flex-1" />
        <button
          type="button"
          aria-label="close project view"
          onClick={() => selectProject(null)}
          className="rounded p-1.5 text-bone-muted hover:bg-ground-2 hover:text-bone"
        >
          <X className="size-4" strokeWidth={1.6} />
        </button>
      </header>

      <div className="flex-1 min-h-0 overflow-y-auto">
        <div className="mx-auto w-full max-w-[44rem] space-y-6 px-6 py-8">
          <section>
            <div className="mb-3 flex items-center gap-3">
              <Sliders className="size-3.5 text-ember" strokeWidth={1.6} />
              <span className="smallcaps">loading strategy</span>
            </div>
            <p className="mb-3 text-sm text-bone-dim">
              How pinned knowledge enters the model's context on every chat turn.
            </p>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
              <ModeCard
                active={project.knowledgeMode === "full"}
                onClick={() => setMode("full")}
                label="full"
                description="Inline each file's full contents until a 10 K-token cap. Largest hit on context."
              />
              <ModeCard
                active={project.knowledgeMode === "preview"}
                onClick={() => setMode("preview")}
                label="preview"
                description="Inline only the first N tokens of each file. Best for many files where headers/leads carry the signal."
              />
              <ModeCard
                active={project.knowledgeMode === "metadata"}
                onClick={() => setMode("metadata")}
                label="metadata"
                description="Only paths and sizes — no file contents. The model uses page_read on demand."
              />
            </div>
            {project.knowledgeMode === "preview" && (
              <div className="mt-3 flex items-center gap-3">
                <label className="text-xs text-bone-dim" htmlFor="preview-tokens">
                  preview tokens per file
                </label>
                <input
                  id="preview-tokens"
                  type="number"
                  min={50}
                  max={5000}
                  step={50}
                  value={draftPreview}
                  onChange={(e) => setDraftPreview(parseInt(e.target.value, 10) || 0)}
                  onBlur={commitPreviewTokens}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") (e.target as HTMLInputElement).blur();
                  }}
                  className="w-24 rounded border border-rule bg-ground-2/40 px-2 py-1 font-mono text-xs text-bone focus:border-ember/60 focus:outline-none"
                />
                <span className="text-[10.5px] text-bone-muted">
                  range 50–5000 · saved on blur
                </span>
              </div>
            )}
          </section>

          <section>
            <div className="mb-3 flex items-center gap-3">
              <BookMarked className="size-3.5 text-ember" strokeWidth={1.6} />
              <span className="smallcaps">knowledge</span>
              <span className="text-xs text-bone-muted">
                {links.length === 0
                  ? "nothing pinned yet"
                  : `${links.length} pinned`}
              </span>
              <span className="flex-1" />
              <button
                type="button"
                onClick={() => openPicker(projectId)}
                className="flex items-center gap-1.5 rounded border border-rule px-2.5 py-1 text-xs text-bone-dim hover:bg-ground-2 hover:text-bone"
              >
                <Plus className="size-3" strokeWidth={1.6} />
                add knowledge
              </button>
            </div>

            <p className="mb-4 text-sm text-bone-dim">
              Pinned pages and folders are loaded into every chat in this
              project as background context (up to ~20 KB; larger items stay
              available via the page tools).
            </p>

            {links.length === 0 ? (
              <button
                type="button"
                onClick={() => openPicker(projectId)}
                className="flex w-full items-center justify-center gap-2 rounded border border-dashed border-rule px-4 py-8 text-sm text-bone-muted hover:border-rule-strong hover:bg-ground-2/40 hover:text-bone-dim"
              >
                <Plus className="size-4" strokeWidth={1.6} />
                pin a page or folder
              </button>
            ) : (
              <ul className="divide-y divide-rule border-y border-rule">
                {links.map((link) => (
                  <li
                    key={link.id}
                    className="group flex items-center gap-3 py-2.5"
                  >
                    {link.ref_type === "page_folder" ? (
                      <Folder
                        className="size-4 shrink-0 text-ember"
                        strokeWidth={1.6}
                      />
                    ) : (
                      <FileText
                        className="size-4 shrink-0 text-bone-muted"
                        strokeWidth={1.6}
                      />
                    )}
                    <span className="min-w-0 flex-1 truncate font-mono text-[11.5px] text-bone-dim">
                      {link.ref_path}
                    </span>
                    <span className="shrink-0 rounded bg-ground-2 px-1.5 py-0.5 font-mono text-[10px] text-bone-muted">
                      {link.ref_type === "page_folder" ? "folder" : "page"}
                    </span>
                    <button
                      type="button"
                      aria-label="unpin"
                      onClick={() =>
                        removeKnowledge(projectId, link.id).catch(() => undefined)
                      }
                      className="shrink-0 rounded p-1 text-bone-muted opacity-0 transition-opacity hover:bg-ground-2 hover:text-red-400 group-hover:opacity-100"
                    >
                      <X className="size-3" strokeWidth={1.6} />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}

function ModeCard({
  active,
  onClick,
  label,
  description,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
  description: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex flex-col gap-1 rounded border px-3 py-2.5 text-left transition-colors",
        active
          ? "border-ember bg-ember-soft/40 text-bone"
          : "border-rule text-bone-dim hover:border-rule-strong hover:bg-ground-2/40 hover:text-bone"
      )}
    >
      <span className="flex items-center gap-2">
        <span className="smallcaps">{label}</span>
        {active && (
          <span className="rounded bg-ember px-1 font-mono text-[9px] uppercase tracking-wide text-ground">
            active
          </span>
        )}
      </span>
      <span className="text-[11px] leading-relaxed text-bone-muted">
        {description}
      </span>
    </button>
  );
}
