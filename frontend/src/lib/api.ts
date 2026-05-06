import type { FileNode } from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export async function fetchTree(): Promise<FileNode> {
  const res = await fetch(`${API_BASE}/api/tree`);
  if (!res.ok) throw new Error(`tree fetch failed: ${res.status}`);
  return res.json();
}

export async function fetchFile(
  path: string
): Promise<{ path: string; content: string; kind: string; lines: number }> {
  const res = await fetch(
    `${API_BASE}/api/file?path=${encodeURIComponent(path)}`
  );
  if (!res.ok) throw new Error(`file fetch failed: ${res.status}`);
  return res.json();
}

export async function uploadFile(file: File, folder = ""): Promise<void> {
  const fd = new FormData();
  fd.append("file", file);
  const url = `${API_BASE}/api/upload${
    folder ? `?folder=${encodeURIComponent(folder)}` : ""
  }`;
  const res = await fetch(url, { method: "POST", body: fd });
  if (!res.ok) throw new Error(`upload failed: ${res.status}`);
}

export const CHAT_URL = `${API_BASE}/api/chat`;
