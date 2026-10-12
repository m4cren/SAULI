"use client";

import { useEffect, useRef, useState } from "react";
import { useClaimant } from "@/hooks/useClaimant";

// The kiosk writes the authoritative state. Poll while this claimant view is
// open, and refresh immediately when the phone returns to the foreground.
export default function useRetrievalPolling(sessionId: string | null) {
  const { refreshRetrieval } = useClaimant();
  const refreshRef = useRef(refreshRetrieval);
  const [syncError, setSyncError] = useState(false);

  useEffect(() => { refreshRef.current = refreshRetrieval; }, [refreshRetrieval]);
  useEffect(() => {
    if (!sessionId) return;
    let active = true;
    let pending = false;
    async function poll() {
      if (!active || pending || document.visibilityState === "hidden") return;
      pending = true;
      try {
        await refreshRef.current();
        if (active) setSyncError(false);
      } catch {
        if (active) setSyncError(true);
      } finally { pending = false; }
    }
    void poll();
    const interval = window.setInterval(() => { void poll(); }, 1000);
    const onVisible = () => { void poll(); };
    window.addEventListener("focus", onVisible);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      active = false;
      window.clearInterval(interval);
      window.removeEventListener("focus", onVisible);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [sessionId]);

  return syncError;
}
