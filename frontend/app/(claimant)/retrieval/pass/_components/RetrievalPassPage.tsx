"use client";

import Link from "next/link";
import BackButton from "@/app/components/BackButton";
import { useClaimant } from "@/hooks/useClaimant";
import QrPlaceholder from "./QrPlaceholder";

export default function RetrievalPassPage() {
  const { state } = useClaimant();
  const item = state.selectedItem;
  if (!item) return <main className="sauli-page"><h1 className="sauli-title">No item selected</h1><Link href="/search/results" className="mt-4 inline-block text-[var(--sauli-brand)]">View search results</Link></main>;
  return <main className="sauli-page flex min-h-[calc(100dvh-148px)] flex-col text-center">
    <div className="text-left"><BackButton href={`/search/results/${item.id}`}>Search Results</BackButton></div>
    <p className="sauli-eyebrow mt-5">PROTOTYPE QR</p>
    <h1 className="sauli-title mx-auto mt-2 max-w-[310px]">Your selected item</h1>
    <p className="sauli-subtitle mt-2">This screen previews the planned retrieval experience.</p>
    <section className="sauli-card mt-10 p-5 text-center"><QrPlaceholder /><p className="mt-4 text-[16px] tracking-[0.08em]">{item.name}</p>
      <p className="mt-2 text-xs text-[#666]">This QR pattern is a placeholder. It cannot authorize item retrieval.</p></section>
    <Link href="/search/results" className="mt-6 inline-flex min-h-11 items-center justify-center rounded-md border border-[var(--sauli-brand)] px-4 text-sm font-semibold text-[var(--sauli-brand)]">Back to results</Link>
  </main>;
}
