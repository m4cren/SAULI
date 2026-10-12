"use client";

import Link from "next/link";
import BackButton from "@/app/components/BackButton";
import useMissingReports from "@/hooks/useMissingReports";
import { formatDateTime } from "@/libs/claimant/format";

export default function MissingReportsPage() {
  const { reports, loading, error, refresh } = useMissingReports();

  return <main className="sauli-page pb-8">
    <BackButton href="/">Home</BackButton>
    <h1 className="sauli-title mt-2">My missing item reports</h1>
    <p className="sauli-subtitle mt-1">Check the current status of items you reported missing.</p>
    {loading && <p role="status" className="mt-5">Loading your reports…</p>}
    {!loading && error && <div role="alert" className="sauli-card mt-5 p-4 text-sm">
      <p>Your reports could not be loaded.</p>
      <button type="button" onClick={refresh} className="mt-2 min-h-11 font-semibold text-[#0B474F] underline">Try again</button>
    </div>}
    {!loading && !error && reports.length === 0 && <section className="sauli-card mt-5 p-5 text-sm">
      <p>You have not posted a missing-item report yet.</p>
      <Link href="/" className="mt-3 inline-flex min-h-11 items-center font-semibold text-[#0B474F] underline">Search for an item</Link>
    </section>}
    {!loading && !error && reports.length > 0 && <ul className="mt-5 space-y-3">
      {reports.map((report) => <li key={report.id}>
        <Link href={`/missing/reports/${report.id}`} className="sauli-card block p-4 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#0B474F]">
          <span className="text-xs font-bold uppercase text-[#0B474F]">{report.status}</span>
          <span className="mt-2 block text-sm font-medium">{report.summary}</span>
          <span className="mt-3 block text-xs text-[#666]">Reported {formatDateTime(report.created_at)}</span>
          <span className="mt-3 block text-sm font-semibold text-[#0B474F]">View current status</span>
        </Link>
      </li>)}
    </ul>}
  </main>;
}
