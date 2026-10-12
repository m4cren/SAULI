"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import BackButton from "@/app/components/BackButton";
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
  const router = useRouter();

  useEffect(() => {
    let active = true;
    void getMissingReport(reportId).then((result) => {
      if (active) { setReport(result); setError(null); }
    }).catch((cause) => {
      if (active) setError(cause instanceof Error ? cause.message : "This report is unavailable.");
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [reportId]);

  async function decide(decision: "confirm" | "reject") {
    if (!report?.candidate || busy) return;
    setBusy(true); setError(null);
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

  return <main className="sauli-page pb-8">
    <BackButton href="/">Home</BackButton>
    <h1 className="sauli-title mt-2">Missing-item report</h1>
    {loading && <p role="status" className="mt-5">Loading your report…</p>}
    {error && <p role="alert" className="mt-5 text-sm text-red-700">{error}</p>}
    {report && <>
      <p className="sauli-subtitle mt-1">{report.status === "active" ? "SAULI is watching for a possible match." : `Report ${report.status}.`}</p>
      <section className="sauli-card mt-5 p-4"><h2 className="text-xs font-bold text-[#0B474F]">YOUR MISSING ITEM</h2><p className="mt-2 text-sm">{report.summary}</p></section>
      {report.candidate ? <section className="sauli-card mt-5 p-4">
        <p className="text-xs font-bold uppercase text-[#267781]">Possible match · Review required</p>
        <div className="mt-4">{report.candidate.front_image_url && !imageFailed ?
          <Image unoptimized src={report.candidate.front_image_url} width={640} height={200} alt={report.candidate.name}
            onError={() => setImageFailed(true)} className="h-[200px] w-full rounded-lg object-contain" /> : <ItemImagePlaceholder large />}</div>
        <h2 className="mt-4 text-xl font-semibold">{report.candidate.name}</h2>
        <p className="mt-2 text-sm">{report.candidate.summary}</p>
        <dl className="mt-4 border-t border-[#ddd] text-sm">
          <div className="flex justify-between gap-3 border-b border-[#ddd] py-3"><dt>Found at</dt><dd className="text-right font-semibold">{report.candidate.found_location}</dd></div>
          <div className="flex justify-between gap-3 py-3"><dt>Date found</dt><dd className="text-right font-semibold">{formatDateTime(report.candidate.found_at)}</dd></div>
        </dl>
        <p className="mt-3 rounded-lg bg-[#e5efef] p-3 text-sm">{report.candidate.explanation}</p>
        <p className="mt-4 text-xs text-[#555]">A possible match does not prove ownership. Review the details before deciding.</p>
        <div className="mt-5 space-y-2"><Button type="button" disabled={busy} onClick={() => void decide("confirm")} className="w-full">This is my item</Button>
          <Button type="button" variant="outline" disabled={busy} onClick={() => void decide("reject")} className="w-full">Not mine</Button></div>
      </section> : <section className="sauli-card mt-5 p-5 text-sm">
        {report.candidate_decision === "accepted" ? "This match was confirmed. Open your retrieval pass to continue." :
          report.candidate_decision === "rejected" ? "You marked the previous item Not mine. SAULI will keep watching for another match." :
          "No unreviewed match is available yet. SAULI will keep monitoring newly placed items."}
      </section>}
    </>}
  </main>;
}
