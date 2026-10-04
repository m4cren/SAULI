"use client";

import Link from "next/link";
import Icon from "@/app/components/Icon";
import { useClaimant } from "@/hooks/useClaimant";

export default function ActiveMissingReport() {
  const { state } = useClaimant();
  const report = state.missingReport;
  if (!report) return <main className="sauli-page"><h1 className="sauli-title">No active report yet</h1><Link href="/" className="mt-4 inline-block text-[var(--sauli-brand)]">Return home</Link></main>;

  return (
    <main className="sauli-page flex min-h-[calc(100dvh-148px)] flex-col pt-[68px] text-center">
      <div className="mx-auto flex size-[65px] items-center justify-center rounded-full bg-[#cde2df] text-[#1a9b8e]"><Icon name="check" size={34} /></div>
      <p className="sauli-eyebrow mt-2">REPORT ACTIVE</p>
      <h1 className="sauli-title mt-3">We’ll watch for a match</h1>
      <p className="sauli-subtitle mt-1">Your missing item is not currently stored in SAULI. We’ll compare it with items added later.</p>
      <section className="sauli-card mt-5 p-2.5 text-left"><h2 className="sauli-eyebrow text-[10px]">SAULI MATCH WATCH</h2><p className="mt-3 text-[12px] leading-[1.35] tracking-[0.04em]">{report.summary}</p><div className="mt-5 rounded-[7px] bg-[#dcefed] px-3 py-3 text-[10px] font-semibold tracking-[0.08em] text-[#287981]">● &nbsp; Monitoring newly scanned items</div></section>
      <p className="mt-9 rounded-[10px] border border-dashed border-[#aaa] p-4 text-left text-[12px] leading-snug text-[#666]">You will receive {report.smsEnabled && report.inAppEnabled ? "SMS and in-app notifications" : report.smsEnabled ? "an SMS notification" : "an in-app notification"} only when a possible match is found. A match does not automatically prove ownership. This prototype does not send notifications.</p>
      <Link href="/" className="sauli-gradient mt-auto inline-flex min-h-12 items-center justify-center rounded-[8px] px-5 py-3 text-[17px] font-semibold text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--sauli-brand)]">Return Home</Link>
    </main>
  );
}
