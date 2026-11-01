"use client";

import Link from "next/link";
import Icon from "@/app/components/Icon";
import { useClaimant } from "@/hooks/useClaimant";
import { maskEmail } from "@/libs/claimant/maskEmail";

export default function ActiveMissingReport() {
  const { state } = useClaimant();
  const report = state.missingReport;

  if (!report) return <main className="client-content py-12 text-center">
    <h1 className="text-3xl font-bold text-[#0b3540]">No active report yet</h1>
    <p className="mt-3 text-[#586276]">Search for your item to start a missing-item report.</p>
    <Link href="/" className="client-primary-button mt-8 inline-flex min-h-12 items-center justify-center rounded-xl px-6 text-white">Return home</Link>
  </main>;

  return <>
    <header className="client-hero text-center">
      <div className="client-hero-body flex flex-col items-center">
        <div role="status" aria-live="polite" className="flex flex-col items-center">
          <span className="flex size-[70px] items-center justify-center rounded-full bg-[#d7fff5] text-[#119c92] shadow-[0_0_30px_rgba(50,240,210,.24)]"><Icon name="check" size={42} /></span>
          <p className="mt-4 text-xs font-bold uppercase tracking-[0.14em] text-[#b8fff3]">Report active</p>
          <h1 className="mt-3 text-[clamp(2.1rem,8vw,3rem)] font-bold leading-[1.1] text-white">We’ll watch for a match</h1>
          <p className="mt-3 max-w-[38ch] text-base leading-relaxed text-white/85">{report.emailEnabled
            ? "SAULI will email you when a possible match is found."
            : "SAULI is monitoring for a possible match. Email alerts are off for this report."}</p>
        </div>
      </div>
    </header>
    <main className="client-content client-overlap min-w-0 pb-24">
      <section className="client-card min-w-0 rounded-[28px] p-5 sm:p-6" aria-labelledby="match-watch-title">
        <p className="mb-4 text-sm font-bold text-[#0b5f70]">Missing item report posted</p>
        <h2 id="match-watch-title" className="flex items-center gap-2 text-sm font-bold uppercase tracking-[0.05em] text-[#075765]"><span aria-hidden="true" className="text-2xl leading-none text-[#10b8ab]">✦</span>SAULI match watch</h2>
        <p className="mt-4 break-words text-base leading-relaxed text-[#252e49]">{report.summary}</p>
        <div className="mt-5 flex items-center gap-3 rounded-[16px] bg-[#dcf5f2] px-4 py-3 text-sm font-semibold text-[#086276]"><span aria-hidden="true" className="size-2.5 shrink-0 rounded-full bg-[#12ac9d] shadow-[0_0_0_5px_rgba(18,172,157,.13)]" />Monitoring newly stored items</div>
      </section>

      <section className="client-info-card mt-5 min-w-0 rounded-[22px] p-5" aria-labelledby="notification-guidance-title">
        <div className="flex items-start gap-3">
          <span aria-hidden="true" className="flex size-12 shrink-0 items-center justify-center rounded-full bg-[#dcf5f2] text-2xl text-[#086276]">✉</span>
          <div className="min-w-0">
            <h2 id="notification-guidance-title" className="text-base font-bold text-[#102d42]">{report.emailEnabled ? "Email notification" : "In-app updates"}</h2>
            {report.emailEnabled ? <p className="mt-2 break-words text-sm leading-relaxed text-[#4d5d75]">We’ll email {maskEmail(report.notificationEmail)} when SAULI finds a possible match. The match will also appear in your SAULI account. A match does not automatically prove ownership.</p>
              : <p className="mt-2 text-sm leading-relaxed text-[#4d5d75]">Email alerts are off for this report. Check your SAULI account for possible matches. A match does not automatically prove ownership.</p>}
          </div>
        </div>
      </section>

      {report.emailEnabled && <section className="mt-5 rounded-[18px] border border-[#cde9e6] bg-white/80 p-4 text-sm leading-relaxed text-[#4d5d75]">
        <h2 className="font-bold text-[#0b4d59]">Notification tip</h2>
        <p className="mt-1">If you do not receive a future match alert, check your Spam or Promotions folder and mark SAULI as “Not spam.” Adding the SAULI sender to your contacts can also help.</p>
      </section>}

      <nav aria-label="Report actions" className="mt-8 flex flex-col gap-3">
        <Link href="/" className="client-primary-button inline-flex min-h-12 items-center justify-center rounded-xl px-5 py-3 text-base font-semibold text-white">Return Home</Link>
        <Link href={`/missing/reports/${report.id}`} className="client-secondary-button inline-flex min-h-12 items-center justify-center rounded-xl px-5 py-3 text-base font-semibold">View my report</Link>
      </nav>
    </main>
  </>;
}
