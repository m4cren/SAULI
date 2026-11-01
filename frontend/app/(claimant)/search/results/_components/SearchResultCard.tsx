"use client";

import { useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { formatShortDate } from "@/libs/claimant/format";
import type { SearchResult } from "@/libs/claimant/types";
import { useClaimant } from "@/hooks/useClaimant";

function MapPinIcon() {
  return <svg aria-hidden="true" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M20 10c0 5-8 11-8 11S4 15 4 10a8 8 0 1 1 16 0Z" /><circle cx="12" cy="10" r="2.5" /></svg>;
}

export default function SearchResultCard({ item, bestMatch = false }: { item: SearchResult; bestMatch?: boolean }) {
  const { selectItem } = useClaimant();
  const [imageFailed, setImageFailed] = useState(false);

  return (
    <Link
      href={`/search/results/${encodeURIComponent(item.id)}`}
      onClick={() => selectItem(item)}
      className={`client-card grid min-w-0 grid-cols-[88px_minmax(0,1fr)] gap-3 p-3 shadow-[0_7px_18px_rgba(7,67,78,0.07)] transition hover:border-[#21b5af] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#087b82] min-[380px]:grid-cols-[106px_minmax(0,1fr)] ${bestMatch ? "border-[#21c0b6]" : ""}`}
    >
      <div className="relative aspect-square w-full overflow-hidden rounded-xl bg-[#e8f0f1]">
        {item.imageUrl && !imageFailed ? (
          <Image unoptimized src={item.imageUrl} fill sizes="(max-width: 379px) 88px, 106px" alt={item.name} onError={() => setImageFailed(true)} className="object-cover" />
        ) : (
          <span role="img" aria-label="No item photo available" className="flex h-full items-center justify-center text-center text-[11px] text-[#60747a]">No photo available</span>
        )}
      </div>
      <div className="min-w-0 self-center">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="rounded-md bg-[#ddf5f2] px-2 py-1 text-[11px] font-bold text-[#066373]">{Math.round(item.matchPercent)}% match</span>
          {bestMatch && <span className="rounded-md bg-[#ddf5f2] px-2 py-1 text-[11px] font-bold text-[#066373]">★ Best match</span>}
        </div>
        <h2 className="mt-2 break-words text-[17px] font-bold leading-tight text-[#0d1d36]">{item.name}</h2>
        <p className="mt-1 flex flex-wrap items-center gap-x-1.5 text-[12px] leading-snug text-[#53627d]">
          <MapPinIcon />
          <span className="min-w-0 break-words">{item.foundLocation}</span>
          <span aria-hidden="true">·</span>
          <span>{formatShortDate(item.foundAt)}</span>
        </p>
        <p className="mt-2 text-[13px] font-bold text-[#006171]">View details <span aria-hidden="true">→</span></p>
      </div>
    </Link>
  );
}
