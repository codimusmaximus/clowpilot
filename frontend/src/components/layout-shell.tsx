"use client";

import { cn } from "@/lib/cn";
import { useUIStore } from "@/lib/ui-store";
import { useChatStore } from "@/lib/chat-store";
import { CopilotRuntimeProvider } from "@/lib/runtime";
import { Sidebar } from "./sidebar";
import { Chat } from "./chat";
import { Workspace } from "./workspace";
import { ResizableSplit } from "./resizable-split";
import { PromptModal } from "./prompt-modal";
import { KnowledgePicker } from "./knowledge-picker";
import { ProjectPage } from "./project-page";
import { SessionInfoModal } from "./session-info-modal";

export function LayoutShell() {
  const sidebarView = useUIStore((s) => s.sidebarView);
  const rightOpen = useUIStore((s) => s.rightOpen);
  const activeProjectId = useChatStore((s) => s.activeProjectId);
  const activeConversationId = useChatStore((s) => s.activeConversationId);
  const showProject = !!activeProjectId && !activeConversationId;

  const mainPane = showProject ? <ProjectPage /> : <Chat />;

  return (
    <div className="grain relative flex h-full">
      <CopilotRuntimeProvider>
        <div
          className={cn(
            "shrink-0 overflow-hidden transition-[width] duration-200 ease-in-out",
            sidebarView !== null ? "w-[272px]" : "w-10"
          )}
        >
          <Sidebar />
        </div>

        {rightOpen ? (
          <ResizableSplit left={mainPane} right={<Workspace />} />
        ) : (
          <div className="h-full min-w-0 flex-1 overflow-hidden">
            {mainPane}
          </div>
        )}

        <PromptModal />
        <KnowledgePicker />
        <SessionInfoModal />
      </CopilotRuntimeProvider>
    </div>
  );
}
