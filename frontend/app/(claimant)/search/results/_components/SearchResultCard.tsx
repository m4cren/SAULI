"use client";

import { useState } from "react";
import Link from "next/link";
import Image from "next/image";
import ItemImagePlaceholder from "@/app/components/ItemImagePlaceholder";
import { formatShortDate } from "@/libs/claimant/format";
import type { SearchResult } from "@/libs/claimant/types";
import { useClaimant } from "@/hooks/useClaimant";

export default function SearchResultCard({ item }: { item: SearchResult }) {
  const { selectItem } = useClaimant();
  const [imageFailed, setImageFailed] = useState(false);
  return <Link href={`/search/results/${item.id}`} onClick={() => selectItem(item)} className="sauli-card flex min-h-[124px] gap-3 p-3 focus-visible:outline-2 focus-visible:outline-[var(--sauli-brand)]">
    {item.imageUrl && !imageFailed ? <Image unoptimized src={item.imageUrl} width={93} height={93} alt={item.name} onError={() => setImageFailed(true)} className="size-[93px] shrink-0 rounded-lg object-cover" /> : <ItemImagePlaceholder />}
    <div className="min-w-0 flex-1">
      <span className="rounded-sm bg-[#e5efef] px-1.5 py-1 text-[10px] font-bold tracking-[0.08em] text-[#267781]">Match rank score {item.matchPercent.toFixed(1)}</span>
      <h2 className="mt-3 truncate text-[17px] font-medium tracking-[0.06em]">{item.name}</h2>
      <p className="truncate text-[10px] font-semibold tracking-[0.03em]">{item.foundLocation} · {formatShortDate(item.foundAt)}</p>
      {item.explanation && <p className="mt-2 line-clamp-2 text-xs text-[#555]">{item.explanation}</p>}
      <p className="mt-3 text-[10px] font-bold tracking-[0.05em]">View details <span aria-hidden="true">→</span></p>
    </div>
  </Link>;
}
