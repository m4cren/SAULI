"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import Image from "next/image";
import ClientHero from "@/app/components/ClientHero";
import Icon from "@/app/components/Icon";
import { formatDateTime } from "@/libs/claimant/format";
import { useClaimant } from "@/hooks/useClaimant";

function MapPinIcon() {
  return <svg aria-hidden="true" width="23" height="23" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M20 10c0 5-8 11-8 11S4 15 4 10a8 8 0 1 1 16 0Z" /><circle cx="12" cy="10" r="2.5" /></svg>;
}

function TagIcon() {
  return <svg aria-hidden="true" width="23" height="23" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M3 4h9l9 9-8 8-10-10V4Z" /><circle cx="8" cy="8" r="1" /></svg>;
}

export default function ItemMatchDetails({ itemId }: { itemId: string }) {
  const { state, rejectCandidate, confirmCandidate } = useClaimant();
  const [imageFailed, setImageFailed] = useState(false);
  const [busy, setBusy] = useState<"confirm" | "reject" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const actionInFlight = useRef(false);
  const router = useRouter();
  const item = state.searchResults.find((result) => result.id === itemId && !state.rejectedCandidateIds.includes(result.id));

  async function decide(decision: "confirm" | "reject") {
    if (!item || actionInFlight.current) return;
    actionInFlight.current = true;
    setBusy(decision);
    setError(null);
    try {
      if (decision === "confirm") {
        await confirmCandidate(item);
        router.push("/retrieval/pass");
      } else {
        await rejectCandidate(item);
        router.push("/search/results");
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Your decision could not be saved. Please try again.");
      actionInFlight.current = false;
      setBusy(null);
    }
  }

  if (!item) {
    return (
      <>
        <ClientHero backHref="/search/results" backLabel="Results" title="Item unavailable" subtitle="This result is no longer in your current search." />
        <main className="client-content client-overlap pb-10">
          <div className="client-card p-6 text-center">
            <p className="text-sm text-[#334257]">Return to the results to search again or choose another item.</p>
            <Link href="/search/results" className="client-primary-button mt-5 flex w-full items-center justify-center">Back to results</Link>
          </div>
        </main>
      </>
    );
  }

  return (
    <>
      <ClientHero backHref="/search/results" backLabel="Results" title="Is this your item?" subtitle="Review the details before confirming." />
      <main className="client-content client-overlap space-y-3 pb-10">
        <section aria-label={item.name} className="client-card overflow-hidden p-2.5 shadow-[0_8px_24px_rgba(7,67,78,0.08)]">
          <div className="relative aspect-[1.48] w-full overflow-hidden rounded-[16px] bg-[#e8f0f1]">
            {item.imageUrl && !imageFailed ? (
              <Image unoptimized src={item.imageUrl} fill sizes="(max-width: 428px) calc(100vw - 58px), 370px" alt={item.name} onError={() => setImageFailed(true)} className="object-cover" />
            ) : (
              <div role="img" aria-label="No item photo available" className="flex h-full items-center justify-center text-sm text-[#60747a]">No photo available</div>
            )}
            <div className="absolute inset-x-3 top-3 flex flex-wrap items-start justify-between gap-2">
              <span className="rounded-xl bg-[#e3f9f6]/95 px-3 py-2 text-sm font-bold text-[#075f6c] shadow-sm">★ {Math.round(item.matchPercent)}% match</span>
              <span className="rounded-xl bg-[#e3f9f6]/95 px-3 py-2 text-sm font-bold text-[#075f6c] shadow-sm">Stored</span>
            </div>
          </div>
          <h2 className="px-2 pb-1 pt-3 text-[24px] font-bold leading-tight text-[#111a32]">{item.name}</h2>
          {item.summary && <p className="px-2 pb-2 text-sm leading-relaxed text-[#4f5c70]">{item.summary}</p>}
        </section>

        <dl className="client-card divide-y divide-[#d7e1e5] px-4 text-sm text-[#111a32] shadow-[0_8px_24px_rgba(7,67,78,0.06)]">
          <div className="flex min-w-0 items-start gap-3 py-4">
            <span className="mt-0.5 shrink-0 text-[#344b65]"><MapPinIcon /></span>
            <dt className="shrink-0 text-[#59647b]">Found at</dt>
            <dd className="ml-auto min-w-0 break-words text-right font-semibold">{item.foundLocation}</dd>
          </div>
          <div className="flex min-w-0 items-start gap-3 py-4">
            <span className="mt-0.5 shrink-0 text-[#344b65]"><Icon name="clock" size={23} /></span>
            <dt className="shrink-0 text-[#59647b]">Date found</dt>
            <dd className="ml-auto min-w-0 break-words text-right font-semibold">{formatDateTime(item.foundAt)}</dd>
          </div>
          <div className="flex min-w-0 items-start gap-3 py-4">
            <span className="mt-0.5 shrink-0 text-[#344b65]"><TagIcon /></span>
            <dt className="shrink-0 text-[#59647b]">Item ID</dt>
            <dd className="ml-auto min-w-0 break-all text-right font-semibold">{item.itemId}</dd>
          </div>
        </dl>

        <aside className="client-info-card flex items-start gap-3 p-4">
          <span aria-hidden="true" className="flex size-10 shrink-0 items-center justify-center rounded-full bg-[#d6f5f1] text-[#086775]"><Icon name="info" size={24} /></span>
          <div>
            <h2 className="font-bold text-[#111a32]">Location protected</h2>
            <p className="mt-1 text-sm leading-snug text-[#59647b]">The exact compartment stays hidden until you confirm this item is yours. A match does not automatically prove ownership.</p>
          </div>
        </aside>

        {(item.explanation || item.matchedAttributes?.length || item.differences?.length) && (
          <details className="client-card px-4 py-3 text-sm text-[#334257]">
            <summary className="cursor-pointer font-semibold text-[#08616d] focus-visible:outline-2 focus-visible:outline-[#087b82]">Why this item matched</summary>
            {item.explanation && <p className="mt-3 leading-relaxed">{item.explanation}</p>}
            {!!item.matchedAttributes?.length && <p className="mt-2"><strong>Matched:</strong> {item.matchedAttributes.join(", ")}</p>}
            {!!item.differences?.length && <p className="mt-2"><strong>Differences:</strong> {item.differences.join(", ")}</p>}
          </details>
        )}

        {error && <p role="alert" className="rounded-xl bg-[#fff2f2] p-3 text-sm text-[#a12424]">{error}</p>}
        <div className="space-y-2 pt-2">
          <button type="button" onClick={() => void decide("confirm")} disabled={busy !== null} className="client-primary-button w-full">
            {busy === "confirm" ? "Preparing retrieval pass…" : "This is my item"}
          </button>
          <button type="button" onClick={() => void decide("reject")} disabled={busy !== null} className="client-secondary-button w-full">
            {busy === "reject" ? "Saving decision…" : "Not mine"}
          </button>
        </div>
      </main>
    </>
  );
}
