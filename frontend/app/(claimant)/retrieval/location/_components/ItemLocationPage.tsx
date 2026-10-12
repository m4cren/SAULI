"use client";

import Icon from "@/app/components/Icon";
import { useClaimant } from "@/hooks/useClaimant";
import useRetrievalPolling from "../../_hooks/useRetrievalPolling";
import ContainerMap from "./ContainerMap";
import WrongItemWarning from "./WrongItemWarning";

export default function ItemLocationPage() {
  const { state } = useClaimant();
  const session = state.retrievalSession;
  const syncError = useRetrievalPolling(session?.id ?? null);

  if (session?.status !== "validated") return <main className="sauli-page" role="status">Opening your retrieval status…</main>;
  if (!session.slotCode || !session.section) return <main className="sauli-page"><h1 className="sauli-title">QR verified</h1><p className="mt-3 text-sm">Waiting for the kiosk to share your storage position.</p>{syncError && <p role="status" className="mt-3 text-sm text-amber-800">Reconnecting to the kiosk status…</p>}</main>;

  const section = session.section === "pocket" ? "Pocket-size" : "Medium-size";
  return <main className="sauli-page pb-9 text-center">
    <div className="mx-auto mt-1 flex size-14 items-center justify-center rounded-full bg-[#d5eae7] text-[#0b7776]"><Icon name="check" size={34} /></div>
    <p className="sauli-eyebrow mt-3">QR verified · Door ready (simulation)</p>
    <h1 className="sauli-title mt-2">Locate your item</h1>
    <p className="sauli-subtitle mt-2">The station accepted your retrieval pass. Your item is in</p>
    <section className="sauli-card mt-5 border-[#5ca7a3] p-5">
      <p className="text-[10px] font-bold uppercase tracking-[0.08em] text-[#287981]">{section} section</p>
      <p className="mt-1 text-5xl font-bold tracking-[-0.06em] text-[#092a2f]">{session.slotCode}</p>
      <p className="mt-2 text-xs text-[#666]">{session.itemSummary}</p>
    </section>
    <ContainerMap highlightedCode={session.slotCode} />
    <ol className="mt-5 space-y-3 text-left text-sm">
      <li className="flex gap-3"><span className="flex size-6 shrink-0 items-center justify-center rounded-full border border-[#0b474f] text-xs">1</span><span><strong>QR verified.</strong><br /><span className="text-xs text-[#555]">Your claim has been accepted at the kiosk.</span></span></li>
      <li className="flex gap-3"><span className="flex size-6 shrink-0 items-center justify-center rounded-full border border-[#0b474f] text-xs">2</span><span><strong>Find position {session.slotCode}.</strong><br /><span className="text-xs text-[#555]">Use the highlighted {section.toLowerCase()} compartment.</span></span></li>
      <li className="flex gap-3"><span className="flex size-6 shrink-0 items-center justify-center rounded-full border border-[#0b474f] text-xs">3</span><span><strong>Lift only your item.</strong><br /><span className="text-xs text-[#555]">The kiosk will record the removal simulation.</span></span></li>
    </ol>
    {syncError && <p role="status" className="mt-5 text-sm text-amber-800">Reconnecting to the kiosk status…</p>}
    {session.wrongItemOut && <WrongItemWarning slotCode={session.slotCode} />}
  </main>;
}
