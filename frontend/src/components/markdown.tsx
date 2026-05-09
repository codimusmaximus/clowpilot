"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { cn } from "@/lib/cn";
import { useWorkspace } from "@/lib/workspace-store";
import { fetchFile } from "@/lib/api";

function isWorkspacePath(href: string | undefined, text: string): string | null {
  // Empty href — treat link text as path
  const candidate = (!href && text) ? text : href;
  if (!candidate) return null;
  // Skip external URLs, anchors, mailto
  if (candidate.includes("://") || candidate.startsWith("#") || candidate.startsWith("mailto:")) return null;
  // Must look like a relative file path (contains a dot-extension or a slash)
  if (/\.\w{1,6}$/.test(candidate) || candidate.includes("/")) return candidate.replace(/^\//, "");
  return null;
}

function WorkspaceAnchor({ href, children }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { children?: React.ReactNode }) {
  const openFile = useWorkspace((s) => s.openFile);
  const text = typeof children === "string" ? children :
    (typeof (children as { props?: { children?: unknown } })?.props?.children === "string"
      ? (children as { props: { children: string } }).props.children
      : "");
  const workspacePath = isWorkspacePath(href, String(text));

  if (workspacePath) {
    return (
      <button
        type="button"
        className="underline decoration-dotted text-ember hover:decoration-solid cursor-pointer"
        onClick={async () => {
          try {
            const f = await fetchFile(workspacePath);
            openFile(f.path, f.content, f.kind);
          } catch {
            console.warn("Could not open workspace file:", workspacePath);
          }
        }}
      >
        {children}
      </button>
    );
  }

  return (
    <a href={href} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  );
}

export function Markdown({
  children,
  className,
}: {
  children: string;
  className?: string;
}) {
  return (
    <div className={cn("prose-chat", className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[[rehypeHighlight, { detect: true, ignoreMissing: true }]]}
        components={{ a: WorkspaceAnchor }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
