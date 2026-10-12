"use client";

import { useEffect, useRef, useState } from "react";
import QRCode from "qrcode";
import Button from "@/app/components/Button";
import { useClaimant } from "@/hooks/useClaimant";
import { retrievalQrFilename, retrievalQrOptions } from "@/libs/retrieval/qr";
import useRetrievalPolling from "../../_hooks/useRetrievalPolling";
import ItemLocationPage from "../../location/_components/ItemLocationPage";
import RetrievedPage from "../../complete/_components/RetrievedPage";

export default function RetrievalPassPage() {
  const { state, replaceRetrieval } = useClaimant();
  const session = state.retrievalSession;
  const syncError = useRetrievalPolling(session?.status === "issued" ? session.id : null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!session?.qrPayload || session.status !== "issued" || !canvas.current) return;
    void QRCode.toCanvas(canvas.current, session.qrPayload, retrievalQrOptions).catch(() => setError("The QR could not be drawn. Replace it and try again."));
  }, [session?.qrPayload, session?.status]);

  async function replace() {
    setBusy(true); setError(null);
    try { await replaceRetrieval(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Could not replace the QR."); }
    finally { setBusy(false); }
  }

  function download() {
    if (!canvas.current || !session?.qrPayload || session.status !== "issued") return;
    const anchor = document.createElement("a");
    anchor.href = canvas.current.toDataURL("image/png");
    anchor.download = retrievalQrFilename;
    anchor.click();
  }

  if (!session) return <main className="sauli-page"><h1 className="sauli-title">No retrieval QR yet</h1><p className="mt-3 text-sm">Confirm a matched item to create a retrieval QR.</p></main>;
  if (session.status === "validated") return <ItemLocationPage />;
  if (session.status === "completed") return <RetrievedPage />;
  const usable = session.status === "issued" && !!session.qrPayload;
  const validMinutes = Math.round((Date.parse(session.expiresAt) - Date.parse(session.issuedAt)) / 60000);
  return <main className="sauli-page pb-8 text-center">
    <h1 className="sauli-title">SAULI retrieval</h1>
    <p className="sauli-subtitle mt-2">Take this one-time QR to the SAULI kiosk.</p>
    <section className="sauli-card mt-7 p-5">
      <h2 className="text-lg font-semibold">{session.itemSummary}</h2>
      {usable ? <>
        <canvas ref={canvas} role="img" aria-label="One-time SAULI retrieval QR" className="mx-auto mt-5 max-w-full rounded-lg border border-[#ddd] bg-white" />
        <p className="mt-4 font-semibold text-[#0B474F]">Valid for {validMinutes === 180 ? "3 hours" : `${validMinutes} minutes`}</p>
        <p className="mt-1 text-sm">Expires {new Date(session.expiresAt).toLocaleString()}</p>
        <Button type="button" onClick={download} className="mt-5 w-full">Download QR as PNG</Button>
        <p className="mt-5 text-left text-sm">At the kiosk, choose Station retrieval and scan this QR with the webcam or upload the downloaded image.</p>
      </> : <div className="mt-6 rounded-lg bg-[#e4e4e4] p-4 text-sm" role="status">
        {session.status === "cancelled" ? "This QR was cancelled." :
          session.status === "expired" ? "This QR has expired." : "This QR is unavailable. Generate a replacement."}
      </div>}
      {(session.status === "issued" || session.status === "expired") && !usable &&
        <Button type="button" disabled={busy} onClick={() => void replace()} className="mt-4 w-full">{busy ? "Replacing…" : "Replace QR"}</Button>}
      {usable && <button type="button" disabled={busy} onClick={() => void replace()} className="mt-4 min-h-11 text-sm font-semibold text-[#0B474F] underline">Lost this QR? Replace it</button>}
      {error && <p role="alert" className="mt-3 text-sm text-red-700">{error}</p>}
      {syncError && <p role="status" className="mt-3 text-sm text-amber-800">Reconnecting to the kiosk status…</p>}
    </section>
  </main>;
}
