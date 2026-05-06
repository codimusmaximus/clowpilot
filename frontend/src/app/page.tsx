import { Sidebar } from "@/components/sidebar";
import { Chat } from "@/components/chat";
import { Workspace } from "@/components/workspace";
import { CopilotRuntimeProvider } from "@/lib/runtime";
import { ResizableSplit } from "@/components/resizable-split";

export default function Home() {
  return (
    <div className="grain relative flex h-full">
      <CopilotRuntimeProvider>
        <div className="w-72 shrink-0">
          <Sidebar />
        </div>
        <ResizableSplit left={<Chat />} right={<Workspace />} />
      </CopilotRuntimeProvider>
    </div>
  );
}
