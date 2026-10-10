"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Image from "next/image";
import BackButton from "@/app/components/BackButton";
import Button from "@/app/components/Button";
import ItemImagePlaceholder from "@/app/components/ItemImagePlaceholder";
import { formatDateTime } from "@/libs/claimant/format";
import { useClaimant } from "@/hooks/useClaimant";

export default function ItemMatchDetails({ itemId }: { itemId: string }) {
  const { state, rejectCandidate, selectItem } = useClaimant();
  const [imageFailed, setImageFailed] = useState(false);
  const router = useRouter();
  const item = state.searchResults.find((result) => result.id === itemId && !state.rejectedCandidateIds.includes(result.id));
  if (!item) return <main className="sauli-page"><BackButton href="/search/results">Results</BackButton><p className="mt-8">This candidate is no longer available in your current search.</p></main>;

  function confirm() { if (item) { selectItem(item); router.push("/retrieval/pass"); } }
  function reject() { if (item) { rejectCandidate(item.id); router.push("/search/results"); } }

  return <main className="sauli-page pb-6">
    <BackButton href="/search/results">Results</BackButton>
    <div className="mt-10">{item.imageUrl && !imageFailed ? <Image unoptimized src={item.imageUrl} width={640} height={195} alt={item.name} onError={() => setImageFailed(true)} className="h-[195px] w-full rounded-lg object-contain" /> : <ItemImagePlaceholder large />}</div>
    <div className="mt-5 flex items-center justify-between text-[11px] font-bold tracking-[0.08em] text-[#267781]"><span>Match rank score {item.matchPercent.toFixed(1)}</span><span>Available</span></div>
    <h1 className="mt-4 text-[26px] font-medium tracking-[0.11em]">{item.name}</h1>
    <dl className="mt-4 border-t border-[#d0d0d0] text-[13px] tracking-[0.04em]">
      <div className="flex justify-between gap-4 border-b border-[#d0d0d0] py-3"><dt className="text-[#555]">Found at</dt><dd className="text-right font-semibold">{item.foundLocation}</dd></div>
      <div className="flex justify-between gap-4 border-b border-[#d0d0d0] py-3"><dt className="text-[#555]">Date found</dt><dd className="text-right font-semibold">{formatDateTime(item.foundAt)}</dd></div>
      <div className="flex justify-between gap-4 border-b border-[#d0d0d0] py-3"><dt className="text-[#555]">Item ID</dt><dd className="text-right font-semibold">{item.itemId}</dd></div>
    </dl>
    {item.summary && <p className="mt-4 text-sm leading-snug">{item.summary}</p>}
    {item.explanation && <p className="mt-4 rounded-lg bg-[#e5efef] p-3 text-sm"><strong>Why this matched: </strong>{item.explanation}</p>}
    {!!item.matchedAttributes?.length && <p className="mt-3 text-sm"><strong>Matched: </strong>{item.matchedAttributes.join(", ")}</p>}
    {!!item.differences?.length && <p className="mt-2 text-sm"><strong>Differences: </strong>{item.differences.join(", ")}</p>}
    <p className="mt-5 rounded-[10px] border border-dashed border-[#aaa] p-3 text-[13px] leading-snug">The match rank score orders results. It does not confirm ownership.</p>
    <div className="mt-8 space-y-2"><Button type="button" onClick={confirm} className="w-full">This is my item</Button><Button type="button" variant="outline" onClick={reject} className="w-full">Not mine</Button></div>
  </main>;
}
