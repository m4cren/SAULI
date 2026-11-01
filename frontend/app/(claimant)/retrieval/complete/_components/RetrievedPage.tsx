"use client";

import Link from "next/link";
import ClientHero from "@/app/components/ClientHero";
import Icon from "@/app/components/Icon";
import { useClaimant } from "@/hooks/useClaimant";
import { formatDateTime } from "@/libs/claimant/format";
import useRetrievalPolling from "../../_hooks/useRetrievalPolling";

export default function RetrievedPage() {
  const { state } = useClaimant();
  const session = state.retrievalSession;
  const receiptComplete = session?.status === "completed" && !!session.slotCode && !!session.completedAt && !!session.retriever;
  const syncError = useRetrievalPolling(receiptComplete ? null : session?.id ?? null);

  if (session?.status !== "completed") return <main className="client-content" role="status">Opening your retrieval receipt…</main>;

  const subtitle = session.slotCode
    ? `The sensor detected that ${session.itemSummary} was lifted from compartment ${session.slotCode}.`
    : "The station recorded that your item was retrieved.";

  return <>
    <ClientHero
      align="center"
      eyebrow="WEIGHT CHANGE DETECTED"
      title="Item retrieved"
      subtitle={subtitle}
      icon={<div className="mx-auto flex size-20 items-center justify-center rounded-full bg-[#dff9f4] text-[#0d9d98] shadow-[0_0_24px_rgba(31,214,195,0.45)]"><Icon name="check" size={48} /></div>}
    />
    <main className="client-content client-overlap space-y-4 pb-8">
      <dl className="client-card overflow-hidden p-1 shadow-[0_12px_28px_rgba(5,81,86,0.08)]">
        <div className="flex min-w-0 justify-between gap-4 border-b border-[#deebed] px-4 py-4"><dt className="shrink-0 text-[#657285]">Item</dt><dd className="min-w-0 break-words text-right font-bold text-[#12243a]">{session.itemSummary}</dd></div>
        <div className="flex min-w-0 justify-between gap-4 border-b border-[#deebed] px-4 py-4"><dt className="shrink-0 text-[#657285]">Compartment</dt><dd className="min-w-0 break-words text-right font-bold text-[#12243a]">{session.slotCode ?? "Updating…"}</dd></div>
        <div className="flex min-w-0 justify-between gap-4 border-b border-[#deebed] px-4 py-4"><dt className="shrink-0 text-[#657285]">Retriever</dt><dd className="min-w-0 break-words text-right font-bold text-[#12243a]">{session.retriever ?? "Your account"}</dd></div>
        <div className="flex min-w-0 justify-between gap-4 px-4 py-4"><dt className="shrink-0 text-[#657285]">Recorded</dt><dd className="min-w-0 break-words text-right font-bold text-[#12243a]">{session.completedAt ? formatDateTime(session.completedAt) : "Updating…"}</dd></div>
      </dl>
      <div className="client-info-card flex items-center gap-3 p-4 text-[#145966]">
        <span aria-hidden="true" className="size-5 shrink-0 rounded-full border-[5px] border-[#bdebe7] bg-[#05a798]" />
        <div><p className="font-bold">Retrieval log saved</p><p className="text-sm text-[#657285]">The transaction is now included in the audit history.</p></div>
      </div>
      {syncError && <p role="status" className="rounded-xl bg-amber-50 p-3 text-sm text-amber-800">Reconnecting to the kiosk status…</p>}
      <div className="grid gap-3 pt-4">
        <Link href="/history" className="client-primary-button flex min-h-12 items-center justify-center">View retrieval history</Link>
        <Link href="/" className="client-secondary-button flex min-h-12 items-center justify-center">Return home</Link>
      </div>
    </main>
  </>;
}
