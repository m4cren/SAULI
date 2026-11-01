"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import Button from "@/app/components/Button";
import ItemImagePlaceholder from "@/app/components/ItemImagePlaceholder";
import { getMissingReport, type MissingReportDetail, type MatchResult } from "@/libs/api/sauli";
import { formatDateTime } from "@/libs/claimant/format";
import type { SearchResult } from "@/libs/claimant/types";
import { useClaimant } from "@/hooks/useClaimant";

function asSearchResult(candidate: MatchResult): SearchResult {
  return { id: candidate.item_id, itemId: candidate.item_id,
    matchCandidateId: candidate.match_candidate_id, name: candidate.name,
    matchPercent: candidate.rank_score, storageStatus: "stored",
    foundLocation: candidate.found_location, foundAt: candidate.found_at,
    summary: candidate.summary, explanation: candidate.explanation,
    matchedAttributes: candidate.matched_attributes,
    differences: candidate.differences, imageUrl: candidate.front_image_url };
}

export default function MissingReportReview({ reportId }: { reportId: string }) {
  const { confirmCandidate, rejectCandidate } = useClaimant();
  const [report, setReport] = useState<MissingReportDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [imageFailed, setImageFailed] = useState(false);
  const [revision, setRevision] = useState(0);
  const router = useRouter();

  useEffect(() => {
    let active = true;
    void getMissingReport(reportId).then((result) => {
      if (active) { setReport(result); setError(null); }
    }).catch((cause) => {
      if (active) setError(cause instanceof Error ? cause.message : "This report is unavailable.");
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [reportId, revision]);

  function refresh() {
    setLoading(true);
    setError(null);
    setReport(null);
    setImageFailed(false);
    setRevision((value) => value + 1);
  }

  async function decide(decision: "confirm" | "reject") {
    if (!report?.candidate || busy) return;
    setBusy(true);
    setError(null);
    try {
      const candidate = asSearchResult(report.candidate);
      if (decision === "confirm") {
        await confirmCandidate(candidate);
        router.push("/retrieval/pass");
      } else {
        await rejectCandidate(candidate);
        setReport(await getMissingReport(reportId));
        setBusy(false);
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The decision could not be saved.");
      setBusy(false);
    }
  }

  const candidate = report && report.status !== "resolved" && report.status !== "cancelled"
    && report.candidate_decision !== "accepted" && report.candidate_decision !== "rejected"
    ? report.candidate : null;
  const statusText = report?.status === "resolved" ? "Item retrieved. Your missing-item report is closed."
    : report?.status === "cancelled" ? "This report was cancelled and is no longer being monitored."
    : candidate ? "Possible match found. Review it below."
    : report?.candidate_decision === "accepted" ? "Match confirmed. Open your retrieval pass to continue."
    : report?.status === "active" ? "SAULI is watching for a possible match."
    : report ? `Report ${report.status}.` : "Check the current status of your report.";

  return <>
    <header className="client-hero">
      <div className="client-hero-body">
        <Link href="/missing/reports" className="client-hero-back"><span aria-hidden="true">←</span>My reports</Link>
        <p className="mt-5 text-xs font-semibold uppercase tracking-[0.16em] text-[#b8fff3]">Match watch</p>
        <h1 className="mt-2 text-[clamp(2rem,8vw,3rem)] font-bold leading-[1.08] text-white">Missing-item report</h1>
        <p className="mt-3 max-w-[38ch] text-base leading-relaxed text-white/85">{statusText}</p>
      </div>
    </header>
    <main className="client-content client-overlap min-w-0 pb-24">
      <button type="button" onClick={refresh} disabled={loading} className="mb-4 min-h-11 text-sm font-semibold text-[#0B474F] underline underline-offset-4 disabled:opacity-60">Refresh status</button>
      {loading && <p role="status" className="client-card rounded-[24px] p-6 text-sm text-[#526174]">Loading your report…</p>}
      {error && <p role="alert" className="mb-4 rounded-xl bg-[#fff1f0] p-4 text-sm text-red-700">{error}</p>}
      {report && !loading && <>
        <section className="client-card rounded-[24px] p-5" aria-labelledby="your-missing-item-title">
          <h2 id="your-missing-item-title" className="text-xs font-bold uppercase tracking-[0.08em] text-[#075765]">Your missing item</h2>
          <p className="mt-3 break-words text-base leading-relaxed text-[#252e49]">{report.summary}</p>
          <span className="mt-4 inline-flex rounded-full bg-[#ddf7f4] px-3 py-1 text-xs font-bold uppercase tracking-[0.05em] text-[#075765]">{report.status}</span>
        </section>
        {candidate ? <section className="client-card mt-5 min-w-0 overflow-hidden rounded-[24px] p-4 sm:p-5" aria-labelledby="possible-match-title">
          <p className="text-xs font-bold uppercase tracking-[0.08em] text-[#087985]">Possible match · Review required</p>
          <div className="mt-4 overflow-hidden rounded-[18px] bg-[#e6eeee]">{candidate.front_image_url && !imageFailed ?
            <Image unoptimized src={candidate.front_image_url} width={640} height={320} alt={candidate.name}
              onError={() => setImageFailed(true)} className="h-[230px] w-full object-contain" /> : <ItemImagePlaceholder large />}</div>
          <h2 id="possible-match-title" className="mt-4 break-words text-xl font-bold leading-snug text-[#101d39]">{candidate.name}</h2>
          <p className="mt-2 break-words text-sm leading-relaxed text-[#526174]">{candidate.summary}</p>
          <dl className="mt-4 divide-y divide-[#d9e3e7] rounded-[16px] border border-[#d9e3e7] px-3 text-sm">
            <div className="flex justify-between gap-3 py-3"><dt className="text-[#647084]">Found at</dt><dd className="text-right font-semibold text-[#101d39]">{candidate.found_location}</dd></div>
            <div className="flex justify-between gap-3 py-3"><dt className="text-[#647084]">Date found</dt><dd className="text-right font-semibold text-[#101d39]">{formatDateTime(candidate.found_at)}</dd></div>
          </dl>
          {candidate.explanation && <p className="mt-4 rounded-[16px] bg-[#e7f7f5] p-4 text-sm leading-relaxed text-[#234b56]">{candidate.explanation}</p>}
          <p className="mt-4 text-sm leading-relaxed text-[#526174]">A possible match does not prove ownership. Review the details before deciding.</p>
          <div className="mt-5 flex flex-col gap-3">
            <Button type="button" disabled={busy} onClick={() => void decide("confirm")} className="client-primary-button w-full">This is my item</Button>
            <Button type="button" variant="outline" disabled={busy} onClick={() => void decide("reject")} className="client-secondary-button w-full">Not mine</Button>
          </div>
        </section> : <section className="client-info-card mt-5 rounded-[22px] p-5 text-sm leading-relaxed text-[#344e5f]">
          {report.status === "resolved" ? "Your item was retrieved successfully. This report is no longer being monitored." :
            report.status === "cancelled" ? "This report was cancelled and is no longer being monitored." :
            report.candidate_decision === "accepted" ? "This match was confirmed. Open your retrieval pass to continue." :
            report.candidate_decision === "rejected" ? "You marked the previous item Not mine. SAULI will keep watching for another match." :
            "No unreviewed match is available yet. SAULI will keep monitoring newly placed items."}
        </section>}
        {report.status !== "resolved" && report.status !== "cancelled" && report.candidate_decision === "accepted" && <Link href="/retrieval/pass" className="client-primary-button mt-5 inline-flex min-h-12 w-full items-center justify-center rounded-xl px-5 py-3 text-base font-semibold text-white">Open your retrieval pass</Link>}
      </>}
    </main>
  </>;
}
