"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import rehypeRaw from "rehype-raw";
import { cn } from "@/lib/cn";
import { useWorkspace } from "@/lib/workspace-store";
import { useUIStore } from "@/lib/ui-store";
import { fetchFile, workspaceImageUrl } from "@/lib/api";

/* ─── [[wiki link]] remark plugin ───────────────────────────────────────── */

type MdastNode = { type: string; value?: string; children?: MdastNode[]; url?: string; title?: string | null };

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const remarkWikiLinks = () => (tree: any) => walkNode(tree);

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
    const [path, alias] = m[1].split("|");
    nodes.push({
      type: "link",
      url: path.trim(),
      title: null,
      children: [{ type: "text", value: (alias ?? path).trim() }],
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

export function WorkspaceAnchor({
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

/* ─── Workspace image ────────────────────────────────────────────────────── */

export function WorkspaceImage({ src, alt }: React.ImgHTMLAttributes<HTMLImageElement>) {
  const resolved = typeof src === "string" && isWorkspaceImageSrc(src)
    ? workspaceImageUrl(normalizeWorkspaceImagePath(src))
    : src;
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={resolved} alt={alt ?? ""} className="max-w-full rounded" />;
}

function isWorkspaceImageSrc(src: string) {
  return !/^(https?:|data:|blob:)/i.test(src);
}

function normalizeWorkspaceImagePath(src: string) {
  if (src.startsWith("file://")) {
    try {
      return decodeURIComponent(new URL(src).pathname);
    } catch {
      return src.replace(/^file:\/\//, "");
    }
  }
  if (src.startsWith("/workspace/")) return src;
  return src.replace(/^\/+/, "");
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
        rehypePlugins={[[rehypeHighlight, { detect: true, ignoreMissing: true }], rehypeRaw]}
        components={{ a: WorkspaceAnchor, img: WorkspaceImage }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
