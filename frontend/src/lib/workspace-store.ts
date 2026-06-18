"use client";

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import type { FileNode, Highlight, ImageTab, Tab } from "./types";

type WorkspaceState = {
  tabs: Tab[];
  activeTabId: string | null;
  highlights: Highlight[];
  tree: FileNode | null;
  pageTree: FileNode | null;
  fileTree: FileNode | null;
  treeLoading: boolean;

  setTree: (tree: FileNode) => void;
  setPageTree: (tree: FileNode) => void;
  setFileTree: (tree: FileNode) => void;
  setTreeLoading: (v: boolean) => void;

  openFile: (
    path: string,
    content: string,
    language: string
  ) => string;
  openSnippet: (
    content: string,
    format: "markdown" | "html",
    title?: string
  ) => string;
  openImage: (path: string, url: string) => string;
  updateFileContent: (path: string, content: string) => void;
  closeFile: (path: string) => void;

  addHighlight: (h: Omit<Highlight, "id" | "createdAt">) => void;
  removeHighlight: (id: string) => void;
  clearHighlightsForPath: (path: string) => void;

  closeTab: (id: string) => void;
  setActive: (id: string) => void;
};

const langFromKind = (kind: string) =>
  ({
    markdown: "markdown",
    python: "python",
    typescript: "typescript",
    javascript: "javascript",
    json: "json",
    yaml: "yaml",
    css: "css",
    html: "html",
    bash: "bash",
    csv: "csv",
    sql: "sql",
    go: "go",
    rust: "rust",
    text: "text",
  })[kind] ?? "text";

const fileTabId = (path: string) => `file:${path}`;
const snippetTabId = () =>
  `snippet:${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`;

export const useWorkspace = create<WorkspaceState>()(
  persist(
    (set) => ({
  tabs: [],
  activeTabId: null,
  highlights: [],
  tree: null,
  pageTree: null,
  fileTree: null,
  treeLoading: false,

  setTree: (tree) => set({ tree }),
  setPageTree: (pageTree) => set({ pageTree }),
  setFileTree: (fileTree) => set({ fileTree }),
  setTreeLoading: (v) => set({ treeLoading: v }),

  openFile: (path, content, language) => {
    const id = fileTabId(path);
    const lang = langFromKind(language);
    set((s) => {
      const existing = s.tabs.find((t) => t.id === id);
      if (existing) {
        return {
          activeTabId: id,
          tabs: s.tabs.map((t) =>
            t.id === id && t.kind === "file"
              ? { ...t, content, language: lang }
              : t
          ),
        };
      }
      return {
        activeTabId: id,
        tabs: [
          ...s.tabs,
          {
            id,
            kind: "file",
            path,
            content,
            language: lang,
            openedAt: Date.now(),
          },
        ],
      };
    });
    return id;
  },

  openImage: (path, url) => {
    const id = `image:${path}`;
    set((s) => {
      const existing = s.tabs.find((t) => t.id === id);
      if (existing) return { activeTabId: id };
      const tab: ImageTab = { id, kind: "image", path, url, openedAt: Date.now() };
      return { activeTabId: id, tabs: [...s.tabs, tab] };
    });
    return id;
  },

  openSnippet: (content, format, title) => {
    const id = snippetTabId();
    set((s) => ({
      activeTabId: id,
      tabs: [
        ...s.tabs,
        {
          id,
          kind: "snippet",
          format,
          content,
          title: title ?? (format === "html" ? "rendered html" : "snippet"),
          openedAt: Date.now(),
        },
      ],
    }));
    return id;
  },

  updateFileContent: (path, content) =>
    set((s) => ({
      tabs: s.tabs.map((t) =>
        t.kind === "file" && t.path === path ? { ...t, content } : t
      ),
    })),

  closeFile: (path) =>
    set((s) => {
      const id = fileTabId(path);
      const tabs = s.tabs.filter((t) => t.id !== id);
      const activeTabId =
        s.activeTabId === id ? tabs.at(-1)?.id ?? null : s.activeTabId;
      return {
        tabs,
        activeTabId,
        highlights: s.highlights.filter((h) => h.path !== path),
      };
    }),

  addHighlight: (h) =>
    set((s) => ({
      highlights: [
        ...s.highlights,
        {
          ...h,
          id: `h:${Date.now().toString(36)}-${Math.random()
            .toString(36)
            .slice(2, 6)}`,
          createdAt: Date.now(),
        },
      ],
    })),

  removeHighlight: (id) =>
    set((s) => ({
      highlights: s.highlights.filter((h) => h.id !== id),
    })),

  clearHighlightsForPath: (path) =>
    set((s) => ({
      highlights: s.highlights.filter((h) => h.path !== path),
    })),

  closeTab: (id) =>
    set((s) => {
      const tabs = s.tabs.filter((t) => t.id !== id);
      const activeTabId =
        s.activeTabId === id ? tabs.at(-1)?.id ?? null : s.activeTabId;
      return { tabs, activeTabId };
    }),

  setActive: (id) => set({ activeTabId: id }),
    }),
    {
      name: "atelier:workspace",
      storage: createJSONStorage(() => localStorage),
      // Persist only the user-visible workspace state; trees are re-fetched.
      partialize: (s) => ({
        tabs: s.tabs,
        activeTabId: s.activeTabId,
        highlights: s.highlights,
      }),
      // Hydrate explicitly on the client (see Workspace mount) to avoid an
      // SSR/client markup mismatch.
      skipHydration: true,
    },
  ),
);
