"use client";

import Link from "next/link";
import Icon from "@/app/components/Icon";
import { useClaimant } from "@/hooks/useClaimant";
import { formatDateTime } from "@/libs/claimant/format";
import useRetrievalPolling from "../../_hooks/useRetrievalPolling";

export default function RetrievedPage() {
  const { state } = useClaimant();
  const session = state.retrievalSession;
  const syncError = useRetrievalPolling(session?.status === "completed" && session.slotCode ? null : session?.id ?? null);

  if (session?.status !== "completed") return <main className="sauli-page" role="status">Opening your retrieval receipt…</main>;

  return <main className="sauli-page flex min-h-[calc(100dvh-170px)] flex-col pb-7 text-center">
    <div className="mx-auto mt-3 flex size-14 items-center justify-center rounded-full bg-[#d5eae7] text-[#0b7776]"><Icon name="check" size={34} /></div>
    <p className="sauli-eyebrow mt-3">Retrieval recorded</p>
    <h1 className="sauli-title mt-2">Item retrieved</h1>
    <p className="sauli-subtitle mt-2">Your item was marked as retrieved at the SAULI kiosk.</p>
    <dl className="sauli-card mt-6 overflow-hidden text-left text-sm">
      <div className="flex justify-between gap-4 border-b border-[#ddd] px-3 py-3"><dt>Item</dt><dd className="text-right font-semibold">{session.itemSummary}</dd></div>
      <div className="flex justify-between gap-4 border-b border-[#ddd] px-3 py-3"><dt>Compartment</dt><dd className="font-semibold">{session.slotCode ?? "Loading…"}</dd></div>
      <div className="flex justify-between gap-4 border-b border-[#ddd] px-3 py-3"><dt>Retriever</dt><dd className="text-right font-semibold">{session.retriever ?? "Your account"}</dd></div>
      <div className="flex justify-between gap-4 px-3 py-3"><dt>Recorded</dt><dd className="text-right font-semibold">{session.completedAt ? formatDateTime(session.completedAt) : "Loading…"}</dd></div>
    </dl>
    <div className="sauli-card mt-4 flex gap-3 p-3 text-left text-xs"><span aria-hidden="true" className="mt-0.5 size-4 shrink-0 rounded-full bg-[#93d3cd]" /><p><strong>Retrieval log saved.</strong><br />The completed transaction is in your retrieval history.</p></div>
    {syncError && <p role="status" className="mt-3 text-sm text-amber-800">Reconnecting to the kiosk status…</p>}
    <div className="mt-auto grid gap-2 pt-8">
      <Link href="/history" className="sauli-gradient flex min-h-12 items-center justify-center rounded-lg px-4 py-3 font-semibold text-white">View retrieval history</Link>
      <Link href="/" className="flex min-h-12 items-center justify-center rounded-lg border border-[#0b474f] px-4 py-3 font-semibold text-[#0b474f]">Return home</Link>
    </div>
  </main>;
}
