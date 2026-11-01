"use client";

import Link from "next/link";
import useMissingReports from "@/hooks/useMissingReports";
import { formatDateTime } from "@/libs/claimant/format";

export default function MissingReportsPage() {
  const { reports, loading, error, refresh } = useMissingReports();

  return <>
    <header className="client-hero">
      <div className="client-hero-body">
        <Link href="/" className="client-hero-back"><span aria-hidden="true">←</span>Home</Link>
        <p className="mt-5 text-xs font-semibold uppercase tracking-[0.16em] text-[#b8fff3]">Match watch</p>
        <h1 className="mt-2 text-[clamp(2rem,8vw,3rem)] font-bold leading-[1.08] text-white">My missing item reports</h1>
        <p className="mt-3 max-w-[38ch] text-base leading-relaxed text-white/85">Check the current status of items you reported missing.</p>
      </div>
    </header>
    <main className="client-content client-overlap min-w-0 pb-24">
      <div aria-live="polite">
        {loading && <p role="status" className="client-card rounded-[24px] p-6 text-center text-sm text-[#526174]">Loading your reports…</p>}
        {!loading && error && <div role="alert" className="client-card rounded-[24px] p-6 text-sm text-[#263848]">
          <p>Your reports could not be loaded.</p>
          <button type="button" onClick={refresh} className="mt-3 min-h-11 font-semibold text-[#0B474F] underline underline-offset-4">Try again</button>
        </div>}
        {!loading && !error && reports.length === 0 && <section className="client-card rounded-[24px] p-6 text-center text-sm text-[#526174]">
          <p>You have not posted a missing-item report yet.</p>
          <Link href="/" className="client-primary-button mt-5 inline-flex min-h-12 items-center justify-center rounded-xl px-6 text-base font-semibold text-white">Search for an item</Link>
        </section>}
        {!loading && !error && reports.length > 0 && <ul className="space-y-4">
          {reports.map((report) => <li key={report.id}>
            <Link href={`/missing/reports/${report.id}`} className="client-card block min-w-0 rounded-[24px] p-5 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#0B474F]">
              <span className={`inline-flex rounded-full px-3 py-1 text-xs font-bold uppercase tracking-[0.07em] ${report.status === "resolved" ? "bg-[#def5ec] text-[#0b675b]" : report.status === "cancelled" ? "bg-[#e9ecf1] text-[#59667c]" : "bg-[#ddf7f4] text-[#075765]"}`}>{report.status}</span>
              <span className="mt-4 block break-words text-[18px] font-bold leading-snug text-[#101d39]">{report.summary}</span>
              <span className="mt-3 block text-sm text-[#647084]">Reported {formatDateTime(report.created_at)}</span>
              <span className="mt-5 block text-sm font-bold text-[#086276]">View current status →</span>
            </Link>
          </li>)}
        </ul>}
      </div>
    </main>
  </>;
}
