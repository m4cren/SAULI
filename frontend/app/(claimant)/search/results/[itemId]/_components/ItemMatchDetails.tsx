"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import BackButton from "@/app/components/BackButton";
import Button from "@/app/components/Button";
import ItemImagePlaceholder from "@/app/components/ItemImagePlaceholder";
import { formatDateTime } from "@/libs/claimant/format";
import { useClaimant } from "@/hooks/useClaimant";

export default function ItemMatchDetails({ itemId }: { itemId: string }) {
  const { state, rejectCandidate, requestRetrievalPass } = useClaimant();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();
  const item = state.searchResults.find((result) => result.id === itemId && !state.rejectedCandidateIds.includes(result.id));

  if (!item) return <main className="sauli-page"><BackButton href="/search/results">Results</BackButton><p className="mt-8">This candidate is no longer available in your current search.</p></main>;

  async function confirm() {
    if (!item) return;
    setPending(true);
    setError(null);
    try {
      await requestRetrievalPass(item);
      router.push("/retrieval/pass");
    } catch {
      setError("Could not prepare a prototype retrieval pass. Try again.");
      setPending(false);
    }
  }

  function reject() {
    if (!item) return;
    rejectCandidate(item.id);
    router.push("/search/results");
  }

  return (
    <main className="sauli-page pb-6">
      <BackButton href="/search/results">Results</BackButton>
      <div className="mt-10"><ItemImagePlaceholder large /></div>
      <div className="mt-5 flex items-center justify-between text-[11px] font-bold tracking-[0.08em] text-[#267781]"><span>{item.matchPercent}% AI MATCH</span><span>Stored</span></div>
      <h1 className="mt-4 text-[26px] font-medium tracking-[0.11em]">{item.name}</h1>
      <dl className="mt-4 border-t border-[#d0d0d0] text-[13px] tracking-[0.04em]">
        <div className="flex justify-between gap-4 border-b border-[#d0d0d0] py-3"><dt className="text-[#555]">Found at</dt><dd className="text-right font-semibold">{item.foundLocation}</dd></div>
        <div className="flex justify-between gap-4 border-b border-[#d0d0d0] py-3"><dt className="text-[#555]">Date found</dt><dd className="text-right font-semibold">{formatDateTime(item.foundAt)}</dd></div>
        <div className="flex justify-between gap-4 border-b border-[#d0d0d0] py-3"><dt className="text-[#555]">Item ID</dt><dd className="text-right font-semibold">{item.itemId}</dd></div>
      </dl>
      <p className="mt-5 rounded-[10px] border border-dashed border-[#aaa] p-3 text-[13px] leading-snug"><strong className="mr-2">Note</strong><span className="text-[#666]">The exact locker location is hidden until you confirm this is your item.</span></p>
      {error && <p role="alert" className="mt-4 text-sm text-red-700">{error}</p>}
      <div className="mt-8 space-y-2"><Button type="button" disabled={pending} onClick={() => void confirm()} className="w-full">{pending ? "Preparing pass…" : "This is my item"}</Button><Button type="button" variant="outline" disabled={pending} onClick={reject} className="w-full">Not mine</Button></div>
    </main>
  );
}
