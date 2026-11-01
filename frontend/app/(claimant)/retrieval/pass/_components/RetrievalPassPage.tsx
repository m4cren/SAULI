"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import QRCode from "qrcode";
import ClientHero from "@/app/components/ClientHero";
import Icon from "@/app/components/Icon";
import { useClaimant } from "@/hooks/useClaimant";
import { retrievalQrFilename, retrievalQrOptions } from "@/libs/retrieval/qr";
import useExpiryCountdown from "../../_hooks/useExpiryCountdown";
import useRetrievalPolling from "../../_hooks/useRetrievalPolling";
import ItemLocationPage from "../../location/_components/ItemLocationPage";
import RetrievedPage from "../../complete/_components/RetrievedPage";

function formatRemaining(seconds: number): string {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const rest = seconds % 60;
  return `${hours}:${String(minutes).padStart(2, "0")}:${String(rest).padStart(2, "0")}`;
}

export default function RetrievalPassPage() {
  const { state, replaceRetrieval } = useClaimant();
  const session = state.retrievalSession;
  const syncError = useRetrievalPolling(session?.status === "issued" ? session.id : null);
  const remaining = useExpiryCountdown(session?.status === "issued" ? session.expiresAt : null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const replacing = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [renderedPayload, setRenderedPayload] = useState<string | null>(null);
  const checkingExpiry = session?.status === "issued" && remaining === null;
  const expired = session?.status === "expired" || remaining === 0 ||
    (session?.status === "issued" && !Number.isFinite(Date.parse(session.expiresAt)));
  const usable = session?.status === "issued" && !!session.qrPayload && !checkingExpiry && !expired;

  useEffect(() => {
    if (!usable || !session?.qrPayload || !canvas.current) return;
    let active = true;
    const target = canvas.current;
    const payload = session.qrPayload;
    const context = target.getContext("2d");
    if (!context) {
      setError("The QR code could not be displayed. Replace it and try again.");
      return;
    }
    context.clearRect(0, 0, target.width, target.height);
    const pendingCanvas = document.createElement("canvas");
    void QRCode.toCanvas(pendingCanvas, payload, retrievalQrOptions).then(() => {
      if (!active) return;
      target.width = pendingCanvas.width;
      target.height = pendingCanvas.height;
      context.drawImage(pendingCanvas, 0, 0);
      setRenderedPayload(payload);
    }).catch(() => {
      if (!active) return;
      context.clearRect(0, 0, target.width, target.height);
      setError("The QR code could not be displayed. Replace it and try again.");
    });
    return () => {
      active = false;
      context.clearRect(0, 0, target.width, target.height);
    };
  }, [session?.qrPayload, usable]);

  async function replace() {
    if (replacing.current) return;
    replacing.current = true;
    setBusy(true);
    setError(null);
    setRenderedPayload(null);
    try {
      await replaceRetrieval();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not replace the QR code.");
    } finally {
      replacing.current = false;
      setBusy(false);
    }
  }

  function download() {
    if (!canvas.current || !session?.qrPayload || session.status !== "issued" || remaining === 0 || renderedPayload !== session.qrPayload || error) return;
    const anchor = document.createElement("a");
    anchor.href = canvas.current.toDataURL("image/png");
    anchor.download = retrievalQrFilename;
    anchor.click();
  }

  if (session?.status === "validated") return <ItemLocationPage />;
  if (session?.status === "completed") return <RetrievedPage />;

  if (!session) {
    return <>
      <ClientHero title="No retrieval pass yet" subtitle="Confirm a matched item to create your one-time QR code." backHref="/search/results" backLabel="Search results" />
      <main className="client-content client-overlap">
        <section className="client-card p-5 text-center">
          <p className="text-sm text-[#526570]">Your retrieval pass will appear here after you confirm an item.</p>
          <Link href="/search/results" className="client-primary-button mt-5 flex min-h-12 items-center justify-center">View search results</Link>
        </section>
      </main>
    </>;
  }

  const duration = Date.parse(session.expiresAt) - Date.parse(session.issuedAt);
  const progress = remaining === null || !Number.isFinite(duration) || duration <= 0
    ? 100 : Math.max(0, Math.min(100, (remaining * 1000 / duration) * 100));

  return <>
    <ClientHero
      align="center"
      eyebrow="RETRIEVAL PASS"
      title="Scan at the SAULI station"
      subtitle="Show this one-time code to the station camera beside the container."
      backHref="/search/results"
      backLabel="Search results"
    />
    <main className="client-content client-overlap space-y-4 pb-8">
      <section className="client-card overflow-hidden p-5 text-center shadow-[0_15px_35px_rgba(5,81,86,0.1)]" aria-label="Retrieval pass">
        <h2 className="sr-only">Retrieval QR for {session.itemSummary}</h2>
        {usable ? <>
          <div className="mx-auto flex w-full max-w-[340px] justify-center rounded-2xl bg-white p-1">
            <canvas ref={canvas} role="img" aria-label="One-time SAULI retrieval QR code" className="block h-auto max-w-full rounded-lg" />
          </div>
          <p className="mt-2 break-words text-xl font-bold text-[#092f37]">{session.itemSummary}</p>
          <p className="mx-auto mt-3 inline-flex items-center gap-2 rounded-full bg-[#e4f7f5] px-4 py-2 text-sm font-semibold text-[#056a72]">
            <span aria-hidden="true">✦</span> One-time code
          </p>
          <div className="mt-4 rounded-2xl bg-[#e6f7f6] px-4 py-4 text-[#075d68]">
            <div className="flex items-center justify-between gap-2">
              <span className="flex items-center gap-2 text-sm font-semibold"><Icon name="clock" size={23} /> Expires in</span>
              <time dateTime={session.expiresAt} role="timer" aria-label={`${remaining === null ? "Calculating" : formatRemaining(remaining)} remaining`} className="font-mono text-2xl font-bold tabular-nums">
                {remaining === null ? "--:--:--" : formatRemaining(remaining)}
              </time>
            </div>
            <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-[#c6eae8]" aria-hidden="true"><div className="h-full rounded-full bg-[#0ba89f]" style={{ width: `${progress}%` }} /></div>
          </div>
        </> : <div role="status" className="rounded-2xl bg-[#e9f0f1] px-5 py-12 text-sm text-[#294d55]">
          <div className="mx-auto mb-4 flex size-14 items-center justify-center rounded-full bg-white text-[#0b7477]"><Icon name="info" size={28} /></div>
          {checkingExpiry ? "Checking retrieval pass…" : expired ? "This retrieval QR has expired. Replace it to continue." : session.status === "cancelled" ? "This retrieval QR was cancelled." : "This QR is unavailable. Generate a replacement."}
        </div>}
        {(expired || (session.status === "issued" && !session.qrPayload)) &&
          <button type="button" disabled={busy} onClick={() => void replace()} className="client-primary-button mt-5 w-full">
            {busy ? "Replacing…" : "Replace QR code"}
          </button>}
      </section>
      {usable && <>
        <section className="client-card flex items-start gap-3 p-4" role="status">
          <span aria-hidden="true" className="mt-1 size-4 shrink-0 rounded-full border-[4px] border-[#ffe2a4] bg-[#f4a820]" />
          <div><h2 className="font-bold text-[#142c39]">Waiting for station scan</h2><p className="mt-1 text-sm text-[#617183]">Keep this screen open and hold the QR code steady.</p></div>
        </section>
        <div className="client-info-card flex items-start gap-3 p-4 text-sm text-[#205663]"><Icon name="info" size={22} className="mt-0.5 shrink-0" /><p>Use this pass only at SAULI. It can be scanned once and does not reveal your compartment until verified.</p></div>
        <button type="button" onClick={download} disabled={renderedPayload !== session.qrPayload || !!error} className="client-secondary-button w-full">{renderedPayload === session.qrPayload ? "Download QR as PNG" : "Preparing QR…"}</button>
        <button type="button" disabled={busy} onClick={() => void replace()} className="mx-auto block min-h-11 px-3 text-sm font-semibold text-[#0B474F] underline underline-offset-4 disabled:opacity-50">Lost this QR? Replace it</button>
      </>}
      {error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-700">{error}</p>}
      {syncError && <p role="status" className="rounded-xl bg-amber-50 p-3 text-sm text-amber-800">Reconnecting to the kiosk status…</p>}
    </main>
  </>;
}
