import { Sidebar } from "@/components/sidebar";
import { Chat } from "@/components/chat";
import { Workspace } from "@/components/workspace";
import { CopilotRuntimeProvider } from "@/lib/runtime";

export default function Home() {
  return (
    <div className="grain relative grid h-full grid-cols-[18rem_minmax(0,1fr)_minmax(28rem,1.4fr)]">
      <CopilotRuntimeProvider>
        <Sidebar />
        <Chat />
        <Workspace />
      </CopilotRuntimeProvider>
    </div>
  );
}
