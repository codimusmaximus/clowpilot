"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ExternalLink, Loader2, Copy, Check } from "lucide-react";
import {
  fetchOutlookStatus,
  startOutlookLogin,
  pollOutlookLogin,
  disconnectOutlook,
  type OutlookStatus,
  type OutlookLogin,
} from "@/lib/api";

export const OUTLOOK_PLUGIN_ID = "ext.outlook";

/**
 * Device-code connect flow for the Outlook plugin. Rendered inside the
 * expanded plugin row in the sidebar.
 */
export function OutlookConnect({ onConnected }: { onConnected?: () => void }) {
  const [status, setStatus] = useState<OutlookStatus | null>(null);
  const [login, setLogin] = useState<OutlookLogin | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const refreshStatus = useCallback(async () => {
    try {
      setStatus(await fetchOutlookStatus());
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    refreshStatus();
    return () => {
      if (pollTimer.current) clearTimeout(pollTimer.current);
    };
  }, [refreshStatus]);

  const poll = useCallback(
    (intervalSec: number) => {
      pollTimer.current = setTimeout(async () => {
        try {
          const res = await pollOutlookLogin();
          if (res.status === "connected") {
            setLogin(null);
            setBusy(false);
            await refreshStatus();
            onConnected?.();
            return;
          }
          if (res.status === "pending") {
            poll(res.interval ?? intervalSec);
            return;
          }
          // expired / error / idle
          setBusy(false);
          setLogin(null);
          if (res.status === "expired") setError("Sign-in code expired — try again.");
          else if (res.status === "error")
            setError(res.detail || res.error || "Sign-in failed.");
        } catch {
          setBusy(false);
          setError("Lost connection while signing in.");
        }
      }, Math.max(2, intervalSec) * 1000);
    },
    [onConnected, refreshStatus]
  );

  const handleConnect = useCallback(async () => {
    setError(null);
    setBusy(true);
    try {
      const info = await startOutlookLogin();
      setLogin(info);
      window.open(info.verificationUri, "_blank", "noopener,noreferrer");
      poll(info.interval);
    } catch (e) {
      setBusy(false);
      setError(e instanceof Error ? e.message : "Could not start sign-in.");
    }
  }, [poll]);

  const handleDisconnect = useCallback(async () => {
    await disconnectOutlook();
    await refreshStatus();
  }, [refreshStatus]);

  const copyCode = useCallback(() => {
    if (!login) return;
    navigator.clipboard?.writeText(login.userCode);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }, [login]);

  if (!status) return null;

  if (!status.configured) {
    return (
      <p className="mt-2 text-[11px] leading-snug text-amber-500/80">
        Not configured — set <code className="font-mono">OUTLOOK_CLIENT_ID</code> in
        the backend env (register a Microsoft Entra app), then restart the backend.
      </p>
    );
  }

  if (status.connected) {
    return (
      <div className="mt-2 flex items-center justify-between gap-2">
        <span className="min-w-0 truncate text-[11px] text-emerald-400/90">
          Connected{status.account ? ` · ${status.account}` : ""}
        </span>
        <button
          type="button"
          onClick={handleDisconnect}
          className="shrink-0 rounded border border-rule px-2 py-0.5 font-mono text-[10px] text-bone-muted hover:border-rule-strong hover:text-bone"
        >
          disconnect
        </button>
      </div>
    );
  }

  return (
    <div className="mt-2 space-y-2">
      {!login && (
        <button
          type="button"
          onClick={handleConnect}
          disabled={busy}
          className="inline-flex items-center gap-1.5 rounded border border-ember/40 px-2 py-1 font-mono text-[10px] text-ember hover:bg-ember-soft/30 disabled:opacity-50"
        >
          {busy ? (
            <Loader2 className="size-3 animate-spin" />
          ) : (
            <ExternalLink className="size-3" />
          )}
          connect outlook
        </button>
      )}

      {login && (
        <div className="rounded border border-ember/25 bg-ember-soft/5 p-2 text-[11px] leading-snug text-bone-muted">
          <p className="mb-1.5">
            Sign in at{" "}
            <a
              href={login.verificationUri}
              target="_blank"
              rel="noopener noreferrer"
              className="text-ember underline"
            >
              {login.verificationUri.replace(/^https?:\/\//, "")}
            </a>{" "}
            and enter this code:
          </p>
          <div className="flex items-center gap-2">
            <code className="rounded bg-ground-2/60 px-2 py-1 font-mono text-[13px] tracking-widest text-bone">
              {login.userCode}
            </code>
            <button
              type="button"
              onClick={copyCode}
              title="copy code"
              className="rounded border border-rule p-1 text-bone-muted hover:text-bone"
            >
              {copied ? <Check className="size-3" /> : <Copy className="size-3" />}
            </button>
            <Loader2 className="size-3 animate-spin text-bone-muted" />
            <span className="text-[10px] text-bone-muted/70">waiting…</span>
          </div>
        </div>
      )}

      {error && <p className="text-[11px] text-red-400/90">{error}</p>}
    </div>
  );
}
