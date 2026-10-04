"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import BackButton from "@/app/components/BackButton";
import Button from "@/app/components/Button";
import StatusCard from "@/app/components/StatusCard";
import { useClaimant } from "@/hooks/useClaimant";
import QrPlaceholder from "./QrPlaceholder";

function clockText(seconds: number) {
  return `${Math.floor(seconds / 60).toString().padStart(2, "0")}:${(seconds % 60).toString().padStart(2, "0")}`;
}

export default function RetrievalPassPage() {
  const { state, markPassExpired, simulateStationQrScan, requestRetrievalPass } = useClaimant();
  const [remaining, setRemaining] = useState(600);
  const [pending, setPending] = useState(false);
  const router = useRouter();
  const pass = state.retrievalPass;

  useEffect(() => {
    if (!pass || state.retrievalStatus !== "waitingForQrScan") return;
    function tick() {
      if (!pass) return;
      const seconds = Math.max(0, Math.ceil((Date.parse(pass.expiresAt) - Date.now()) / 1000));
      setRemaining(seconds);
      if (seconds === 0) markPassExpired();
    }
    tick();
    const timer = window.setInterval(tick, 1000);
    return () => window.clearInterval(timer);
  }, [pass, state.retrievalStatus, markPassExpired]);

  if (!pass || !state.selectedItem) return <main className="sauli-page"><h1 className="sauli-title">No retrieval pass yet</h1><Link href="/search/results" className="mt-4 inline-block text-[var(--sauli-brand)]">View search results</Link></main>;

  async function renew() {
    if (!state.selectedItem) return;
    setPending(true);
    try { await requestRetrievalPass(state.selectedItem); setRemaining(600); }
    finally { setPending(false); }
  }

  function scan() {
    if (simulateStationQrScan()) router.push("/retrieval/location");
  }

  const expired = state.retrievalStatus === "qrExpired" || remaining === 0;
  return (
    <main className="sauli-page flex min-h-[calc(100dvh-148px)] flex-col text-center">
      <div className="text-left"><BackButton href={`/search/results/${state.selectedItem.id}`}>Search Results</BackButton></div>
      <p className="sauli-eyebrow mt-5">RETRIEVAL PASS</p>
      <h1 className="sauli-title mx-auto mt-2 max-w-[310px]">Scan at the SAULI station</h1>
      <p className="sauli-subtitle mt-2">Present this temporary code to the Raspberry Pi camera beside the container.</p>
      <section className="sauli-card mt-10 p-3 text-center">
        <QrPlaceholder />
        <p className="mt-4 text-[16px] tracking-[0.08em]">{pass.itemName}</p>
        <p className="mt-1 text-[10px] text-[#777]">Prototype QR placeholder — not scannable</p>
        <div aria-live="polite" className="mt-3 flex justify-between rounded-lg bg-[#dcefed] px-2.5 py-2 text-[12px] font-semibold text-[#267781]"><span>{expired ? "QR expired" : "QR expires in"}</span><span>{expired ? "00:00" : clockText(remaining)}</span></div>
      </section>
      <div className="mt-5"><StatusCard icon={<span className="size-3 rounded-full bg-[#efaa37]" />} title={expired ? "Pass expired" : "Waiting for station scan"}>{expired ? "Create a new prototype pass to continue." : "The code can only be used once."}</StatusCard></div>
      <div className="mt-auto pt-8">
        {expired ? <Button type="button" disabled={pending} onClick={() => void renew()} className="w-full">{pending ? "Preparing…" : "Request new prototype pass"}</Button> : <Button type="button" onClick={scan} className="w-full">Simulate station QR scan</Button>}
        <p className="mt-3 text-[10px] leading-snug text-[#777]">Prototype control: the real station must validate a server-issued one-time token.</p>
      </div>
    </main>
  );
}
