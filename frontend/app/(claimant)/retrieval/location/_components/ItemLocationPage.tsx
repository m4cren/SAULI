"use client";

import ClientHero from "@/app/components/ClientHero";
import Icon from "@/app/components/Icon";
import { useClaimant } from "@/hooks/useClaimant";
import { isSlotCode } from "@/libs/storage/slots";
import useRetrievalPolling from "../../_hooks/useRetrievalPolling";
import ContainerMap from "./ContainerMap";
import WrongItemWarning from "./WrongItemWarning";

function positionDescription(code: string): string {
  const number = Number(code.slice(2));
  if (!Number.isInteger(number) || number < 1) return "Ask SAULI staff for directions";
  if (code.startsWith("P-")) {
    return `Left cabinet · Row ${Math.ceil(number / 2)} · ${number % 2 ? "Left" : "Right"} slot`;
  }
  return `Center cabinet · Row ${number}`;
}

export default function ItemLocationPage() {
  const { state } = useClaimant();
  const session = state.retrievalSession;
  const syncError = useRetrievalPolling(session?.id ?? null);

  if (session?.status !== "validated") return <main className="client-content" role="status">Opening your retrieval status…</main>;
  if (!session.slotCode || !session.section) {
    return <>
      <ClientHero align="center" eyebrow="QR VERIFIED" title="Locating your item" subtitle="The kiosk is sharing your assigned position." icon={<div className="mx-auto flex size-16 items-center justify-center rounded-full bg-[#dff9f4] text-[#0d9d98]"><Icon name="check" size={40} /></div>} />
      <main className="client-content client-overlap"><p role="status" className="client-card p-5 text-center text-sm">Waiting for the kiosk to share your storage position.</p>{syncError && <p role="status" className="mt-4 text-sm text-amber-800">Reconnecting to the kiosk status…</p>}</main>
    </>;
  }

  const currentPosition = isSlotCode(session.slotCode);
  const section = session.section === "pocket" ? "Pocket-size" : "Medium-size";

  return <>
    <ClientHero
      align="center"
      eyebrow={currentPosition ? "QR VERIFIED · DOOR READY" : "QR VERIFIED · STAFF ASSISTANCE NEEDED"}
      title={currentPosition ? "Locate your item" : "Ask staff for your item"}
      subtitle={currentPosition ? "Your item is inside the highlighted compartment." : "This position is retired from the current cabinet."}
      icon={<div className="mx-auto flex size-18 items-center justify-center rounded-full bg-[#dff9f4] text-[#0d9d98] shadow-[0_0_22px_rgba(31,214,195,0.45)]"><Icon name="check" size={44} /></div>}
    />
    <main className="client-content client-overlap pb-8">
      <section className="client-card border-[#d6eff0] p-5 text-center shadow-[0_12px_28px_rgba(5,81,86,0.08)]">
        <p className="text-xs font-bold uppercase tracking-[0.08em] text-[#116c78]">{section} section</p>
        <p className="mt-1 text-6xl font-bold tracking-[-0.05em] text-[#101e2a]">{session.slotCode}</p>
        <p className="mt-2 text-sm text-[#657285]">{positionDescription(session.slotCode)}</p>
      </section>
      <ContainerMap highlightedCode={session.slotCode} />
      {currentPosition ? <ol className="mt-5 space-y-0 px-1 text-sm text-[#142b3a]">
        <li className="flex gap-4 border-b border-[#dfebed] py-3"><span className="flex size-8 shrink-0 items-center justify-center rounded-full border border-[#0b474f] text-sm font-bold">1</span><span><strong>QR code verified</strong><br /><span className="text-[#657285]">Your retrieval pass was accepted.</span></span></li>
        <li className="flex gap-4 border-b border-[#dfebed] py-3"><span className="flex size-8 shrink-0 items-center justify-center rounded-full border border-[#0b474f] text-sm font-bold">2</span><span><strong>Open the {section.toLowerCase()} door</strong><br /><span className="text-[#657285]">Follow the highlighted compartment {session.slotCode}.</span></span></li>
        <li className="flex gap-4 py-3"><span className="flex size-8 shrink-0 items-center justify-center rounded-full border border-[#0b474f] text-sm font-bold">3</span><span><strong>Lift only your item</strong><br /><span className="text-[#657285]">The sensor confirms when it is removed.</span></span></li>
      </ol> : <p className="client-info-card mt-4 p-4 text-sm">Show this position and your retrieval pass to SAULI staff. Do not try another compartment.</p>}
      {syncError && <p role="status" className="mt-4 rounded-xl bg-amber-50 p-3 text-sm text-amber-800">Reconnecting to the kiosk status…</p>}
    </main>
    {session.wrongItemOut && <WrongItemWarning slotCode={session.slotCode} itemSummary={session.itemSummary} />}
  </>;
}
