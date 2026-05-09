"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

export type SidebarView = "explorer" | "settings" | null;

type UIState = {
  sidebarView: SidebarView;
  lastSidebarView: Exclude<SidebarView, null>;
  rightOpen: boolean;
  promptModalOpen: boolean;

  toggleSidebarView: (v: Exclude<SidebarView, null>) => void;
  collapseSidebar: () => void;
  expandSidebar: () => void;
  setRightOpen: (v: boolean) => void;
  toggleRight: () => void;
  openPromptModal: () => void;
  closePromptModal: () => void;
};

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      sidebarView: "explorer" as SidebarView,
      lastSidebarView: "explorer" as Exclude<SidebarView, null>,
      rightOpen: true,
      promptModalOpen: false,

      toggleSidebarView: (v) =>
        set((s) => ({
          sidebarView: s.sidebarView === v ? null : v,
          lastSidebarView: v,
        })),
      collapseSidebar: () =>
        set((s) => ({
          sidebarView: null,
          lastSidebarView: s.sidebarView ?? s.lastSidebarView,
        })),
      expandSidebar: () =>
        set((s) => ({ sidebarView: s.lastSidebarView })),
      setRightOpen: (v) => set({ rightOpen: v }),
      toggleRight: () => set((s) => ({ rightOpen: !s.rightOpen })),
      openPromptModal: () => set({ promptModalOpen: true }),
      closePromptModal: () => set({ promptModalOpen: false }),
    }),
    {
      name: "copilot-ui-state",
      version: 2,
      migrate: (raw) => {
        const s = raw as Record<string, unknown>;
        if (s.sidebarView === "threads" || s.sidebarView === "files") {
          s.sidebarView = "explorer";
          s.lastSidebarView = "explorer";
        }
        return s as UIState;
      },
      partialize: (s) => ({
        sidebarView: s.sidebarView,
        lastSidebarView: s.lastSidebarView,
        rightOpen: s.rightOpen,
      }),
    }
  )
);
