"use client";

import Link from "next/link";
import useMissingReports from "@/hooks/useMissingReports";

export default function MissingReportsShortcut() {
  const { reports, loading, error, refresh } = useMissingReports();

  if (loading) return null;
  if (error) return <div className="mt-5 text-sm text-[#555]" role="status">
    Could not check your missing-item reports. <button type="button" onClick={refresh} className="min-h-11 font-semibold text-[#0B474F] underline">Try again</button>
  </div>;
  if (reports.length === 0) return null;

  const href = reports.length === 1 ? `/missing/reports/${reports[0].id}` : "/missing/reports";
  return <Link href={href} className="sauli-card mt-5 flex min-h-16 items-center justify-between gap-3 p-4 text-[#0B474F] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#0B474F]">
    <span><strong className="block text-base">My missing item {reports.length === 1 ? "report" : "reports"}</strong><span className="block text-sm">View current status</span></span>
    <span aria-hidden="true" className="text-xl">›</span>
  </Link>;
}
