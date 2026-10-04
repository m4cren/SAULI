"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import Icon from "@/app/components/Icon";
import { useClaimant } from "@/hooks/useClaimant";
import { useAuth } from "@/hooks/useAuth";
import { displayName } from "@/libs/types/auth";
import ContainerMap from "./ContainerMap";
import PrototypeSensorControls from "./PrototypeSensorControls";
import WrongItemModal from "./WrongItemModal";

export default function ItemLocationPage() {
  const { state, simulateWrongItemLifted, simulateWrongItemReturned, simulateCorrectItemLifted } = useClaimant();
  const { user } = useAuth();
  const router = useRouter();
  const modalOpen = state.retrievalStatus === "waitingForWrongItemReturn";

  if (!state.retrievalPass || !["waitingForCorrectItem", "waitingForWrongItemReturn"].includes(state.retrievalStatus)) {
    return <main className="sauli-page"><h1 className="sauli-title">Station scan required</h1><p className="mt-3 text-sm">Use the prototype station scan control on your retrieval pass first.</p><Link href="/retrieval/pass" className="mt-4 inline-block text-[var(--sauli-brand)]">View retrieval pass</Link></main>;
  }

  function correctItemLifted() {
    simulateCorrectItemLifted(user ? displayName(user) : "SAULI user");
    router.push("/retrieval/complete");
  }

  return (
    <>
      <main inert={modalOpen} aria-hidden={modalOpen} className="sauli-page pb-6 text-center">
        <div className="mx-auto mt-3 flex size-[65px] items-center justify-center rounded-full bg-[#cde2df] text-[#1a9b8e]"><Icon name="check" size={34} /></div>
        <p className="sauli-eyebrow mt-1">QR VERIFIED · DOOR READY</p>
        <h1 className="sauli-title mt-1">Locate your item</h1>
        <p className="sauli-subtitle mt-1">The station accepted your retrieval pass. Your item is in</p>
        <section className="mt-5 rounded-[8px] border border-[#2c737b] bg-white px-3 py-5"><p className="sauli-eyebrow text-[11px]">POCKET-SIZE SECTION</p><p className="mt-1 text-[49px] font-bold leading-none text-[#333]">P-05</p><p className="mt-1 text-[11px] text-[#888]">Left cabinet · Row C · Pocket 05</p></section>
        <ContainerMap />
        <ol className="mt-3 space-y-2 text-left">{[
          ["QR code verified", "Your identity and claim have been accepted"],
          ["Open the pocket-size door", "Follow the highlighted location to compartment P-05."],
          ["Lift only your item", "The station will confirm the removal."],
        ].map(([title, description], index) => <li key={title} className="flex items-start gap-2"><span className="flex size-7 shrink-0 items-center justify-center rounded-full border border-[#333] text-sm">{index + 1}</span><span><strong className="block text-[13px] font-medium tracking-[0.06em]">{title}</strong><span className="block text-[10px] tracking-[0.05em] text-[#666]">{description}</span></span></li>)}</ol>
        <PrototypeSensorControls simulateWrongItemLifted={simulateWrongItemLifted} simulateCorrectItemLifted={correctItemLifted} />
        <p aria-live="polite" className="sr-only">Waiting for P-05, Black leather wallet.</p>
      </main>
      {modalOpen && <WrongItemModal onReturned={simulateWrongItemReturned} />}
    </>
  );
}
