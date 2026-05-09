"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { cn } from "@/lib/cn";
import { useWorkspace } from "@/lib/workspace-store";
import { useUIStore } from "@/lib/ui-store";
import { fetchFile } from "@/lib/api";

/* ─── [[wiki link]] remark plugin ───────────────────────────────────────── */

type MdastNode = { type: string; value?: string; children?: MdastNode[]; url?: string; title?: string | null };

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const remarkWikiLinks = () => (tree: any) => walkNode(tree);

function walkNode(parent: MdastNode) {
  if (!parent.children) return;
  let i = 0;
  while (i < parent.children.length) {
    const child = parent.children[i];
    if (child.type === "text" && child.value) {
      const replacements = splitWikiLinks(child.value);
      if (replacements.length !== 1 || replacements[0] !== child) {
        parent.children.splice(i, 1, ...replacements);
        i += replacements.length;
        continue;
      }
    } else {
      walkNode(child);
    }
    i++;
  }
}

function splitWikiLinks(text: string): MdastNode[] {
  const re = /\[\[([^\]]+)\]\]/g;
  if (!re.test(text)) return [{ type: "text", value: text }];
  re.lastIndex = 0;
  const nodes: MdastNode[] = [];
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) nodes.push({ type: "text", value: text.slice(last, m.index) });
    nodes.push({
      type: "link",
      url: m[1],
      title: null,
      children: [{ type: "text", value: m[1] }],
    });
    last = m.index + m[0].length;
  }
  if (last < text.length) nodes.push({ type: "text", value: text.slice(last) });
  return nodes;
}

/* ─── Workspace anchor ───────────────────────────────────────────────────── */

function isWorkspacePath(href: string | undefined, text: string): string | null {
  const candidate = !href ? text : href;
  if (!candidate) return null;
  if (candidate.includes("://") || candidate.startsWith("#") || candidate.startsWith("mailto:")) return null;
  if (/\.\w{1,6}$/.test(candidate) || candidate.includes("/")) return candidate.replace(/^\//, "");
  return null;
}

function WorkspaceAnchor({
  href,
  children,
}: React.AnchorHTMLAttributes<HTMLAnchorElement> & { children?: React.ReactNode }) {
  const openFile = useWorkspace((s) => s.openFile);
  const setRightOpen = useUIStore((s) => s.setRightOpen);

  const text =
    typeof children === "string"
      ? children
      : (typeof (children as { props?: { children?: unknown } })?.props?.children === "string"
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
            setRightOpen(true);
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

/* ─── Markdown renderer ──────────────────────────────────────────────────── */

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
        remarkPlugins={[remarkGfm, remarkWikiLinks]}
        rehypePlugins={[[rehypeHighlight, { detect: true, ignoreMissing: true }]]}
        components={{ a: WorkspaceAnchor }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
