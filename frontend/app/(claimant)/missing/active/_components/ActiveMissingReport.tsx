"use client";

import Link from "next/link";
import Icon from "@/app/components/Icon";
import { useClaimant } from "@/hooks/useClaimant";
import { maskEmail } from "@/libs/claimant/maskEmail";

export default function ActiveMissingReport() {
  const { state } = useClaimant();
  const report = state.missingReport;
  if (!report) return <main className="sauli-page"><h1 className="sauli-title">No active report yet</h1><Link href="/" className="mt-4 inline-block text-[var(--sauli-brand)]">Return home</Link></main>;

  return (
    <main className="sauli-page flex min-h-[calc(100dvh-148px)] min-w-0 flex-col pt-10 text-center">
      <div role="status" aria-live="polite">
        <div className="mx-auto flex size-[65px] items-center justify-center rounded-full bg-[#cde2df] text-[#1a9b8e]"><Icon name="check" size={34} /></div>
        <p className="sauli-eyebrow mt-2">REPORT ACTIVE</p>
        <h1 className="sauli-title mt-3">Missing item report posted</h1>
        <p className="sauli-subtitle mt-2">{report.emailEnabled
          ? "SAULI will email you when a possible match is found."
          : "SAULI is monitoring for a possible match. Email alerts are off for this report."}</p>
      </div>
      <section className="sauli-card mt-6 min-w-0 p-4 text-left">
        <h2 className="sauli-eyebrow text-[10px]">SAULI MATCH WATCH</h2>
        <p className="mt-3 break-words text-[12px] leading-[1.4] tracking-[0.04em]">{report.summary}</p>
        <p className="mt-4 break-all text-xs text-[#0B474F]">Notification email: <span className="font-semibold">{maskEmail(report.notificationEmail)}</span></p>
        <div className="mt-4 rounded-[7px] bg-[#dcefed] px-3 py-3 text-xs font-semibold text-[#287981]">Monitoring newly stored items</div>
      </section>
      <section className="mt-5 min-w-0 rounded-[10px] border border-dashed border-[#aaa] p-4 text-left text-[12px] leading-snug text-[#555]">
        <h2 className="font-semibold text-[#0B474F]">Notification tip</h2>
        <p className="mt-2">If you do not receive a future match alert, check your Spam or Promotions folder and mark SAULI as “Not spam.” Adding the SAULI sender to your contacts can also help.</p>
      </section>
      <p className="mt-4 text-left text-xs text-[#666]">A possible match does not prove ownership. You will review the item before retrieval.</p>
      <nav aria-label="Report actions" className="mt-auto flex flex-col gap-2 pt-8">
        <Link href={`/missing/reports/${report.id}`} style={{ background: "linear-gradient(180deg, #299F93 0%, #0B474F 100%)" }} className="inline-flex min-h-12 items-center justify-center rounded-[8px] px-5 py-3 text-[17px] font-semibold text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--sauli-brand)]">View my report</Link>
        <Link href="/" className="inline-flex min-h-12 items-center justify-center rounded-[8px] border border-[#0B474F] px-5 py-3 text-[17px] font-semibold text-[#0B474F] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--sauli-brand)]">Back to home</Link>
      </nav>
    </main>
  );
}
