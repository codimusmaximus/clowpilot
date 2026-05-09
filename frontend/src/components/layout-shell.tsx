"use client";

import { cn } from "@/lib/cn";
import { useUIStore } from "@/lib/ui-store";
import { CopilotRuntimeProvider } from "@/lib/runtime";
import { Sidebar } from "./sidebar";
import { Chat } from "./chat";
import { Workspace } from "./workspace";
import { ResizableSplit } from "./resizable-split";
import { PromptModal } from "./prompt-modal";

export function LayoutShell() {
  const sidebarView = useUIStore((s) => s.sidebarView);
  const rightOpen = useUIStore((s) => s.rightOpen);

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
          <ResizableSplit left={<Chat />} right={<Workspace />} />
        ) : (
          <div className="h-full min-w-0 flex-1 overflow-hidden">
            <Chat />
          </div>
        )}

        <PromptModal />
      </CopilotRuntimeProvider>
    </div>
  );
}
