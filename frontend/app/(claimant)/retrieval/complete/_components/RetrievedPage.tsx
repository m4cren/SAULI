"use client";

import Link from "next/link";
import Icon from "@/app/components/Icon";
import StatusCard from "@/app/components/StatusCard";
import { useClaimant } from "@/hooks/useClaimant";
import { formatDateTime } from "@/libs/claimant/format";

export default function RetrievedPage() {
  const { state } = useClaimant();
  const record = state.retrievalStatus === "retrieved" ? state.retrievalHistory[0] : null;

  if (!record) {
    return <main className="sauli-page"><h1 className="sauli-title">No completed retrieval</h1><p className="mt-3 text-sm">A retrieval appears here after the prototype detects the correct item.</p><Link href="/history" className="mt-4 inline-block text-[var(--sauli-brand)]">View retrieval history</Link></main>;
  }

  return (
    <main className="sauli-page flex min-h-[calc(100dvh-148px)] flex-col text-center">
      <div className="mx-auto mt-3 flex size-[65px] items-center justify-center rounded-full bg-[#cde2df] text-[#1a9b8e]"><Icon name="check" size={34} /></div>
      <p className="sauli-eyebrow mt-2">WEIGHT CHANGE DETECTED</p>
      <h1 className="sauli-title mt-1">Item retrieved</h1>
      <p className="sauli-subtitle mt-1">The prototype detected that the {record.itemName.toLowerCase()} was lifted from compartment {record.compartmentId}.</p>
      <dl className="sauli-card mt-5 overflow-hidden text-left text-[13px] tracking-[0.04em]">
        {[["Item", record.itemName], ["Compartment", record.compartmentId], ["Retriever", record.retriever], ["Recorded", formatDateTime(record.recordedAt)]].map(([label, value], index) => (
          <div key={label} className={`flex min-h-[46px] items-center justify-between gap-3 px-3 py-2 ${index ? "border-t border-[var(--sauli-border)]" : ""}`}><dt className="text-[#555]">{label}</dt><dd className="text-right font-semibold">{value}</dd></div>
        ))}
      </dl>
      <div className="mt-5 text-left"><StatusCard icon={<span className="size-3 rounded-full bg-[#1a9b8e]" />} title="Retrieval log saved">This prototype record is now in your retrieval history.</StatusCard></div>
      <div className="mt-auto space-y-2 pt-10">
        <Link href="/history" className="sauli-gradient flex min-h-12 items-center justify-center rounded-[8px] px-4 text-[17px] font-semibold text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--sauli-brand)]">View retrieval history</Link>
        <Link href="/" className="flex min-h-12 items-center justify-center rounded-[8px] border border-[var(--sauli-brand)] px-4 text-[17px] font-semibold text-[var(--sauli-brand)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--sauli-brand)]">Return home</Link>
      </div>
    </main>
  );
}
