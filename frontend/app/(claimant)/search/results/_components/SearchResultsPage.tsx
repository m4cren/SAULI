"use client";

import Link from "next/link";
import ClientHero from "@/app/components/ClientHero";
import Icon from "@/app/components/Icon";
import { useClaimant } from "@/hooks/useClaimant";
import SearchResultCard from "./SearchResultCard";

export default function SearchResultsPage() {
  const { state, runSearch } = useClaimant();
  const visible = state.searchResults.filter((item) => !state.rejectedCandidateIds.includes(item.id));
  const allRejected = state.searchStatus === "results" && state.searchResults.length > 0 && visible.length === 0;
  const hasSearch = state.searchStatus === "results" || state.searchStatus === "empty";
  const count = visible.length;
  const subtitle = hasSearch
    ? `${count} possible ${count === 1 ? "match" : "matches"}`
    : state.searchStatus === "searching"
      ? "Searching available items…"
      : "Find your missing item";

  return (
    <>
      <ClientHero backHref="/" backLabel="New search" title="Search results" subtitle={subtitle} />
      <main className="client-content client-overlap space-y-4 pb-10">
        <p role="status" className="sr-only">{subtitle}</p>
        <section aria-label="Your search" className="client-card flex min-h-16 items-center gap-3 px-4 py-3 shadow-[0_8px_20px_rgba(7,67,78,0.09)]">
          <p className="min-w-0 flex-1 break-words text-[15px] leading-snug text-[#17253e]">
            {state.searchDraft.description || "No search description yet"}
          </p>
          <Link href="/search/filters" className="inline-flex min-h-11 shrink-0 items-center rounded-md px-2 font-semibold text-[#08616d] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#087b82]">
            Edit
          </Link>
        </section>

        {state.searchStatus === "searching" && (
          <div role="status" className="client-card p-6 text-center text-sm text-[#334257]">Searching available items…</div>
        )}
        {state.searchStatus === "idle" && (
          <div className="client-card p-6 text-center">
            <p className="text-sm text-[#334257]">Start with a description to find possible matches.</p>
            <Link href="/" className="mt-3 inline-flex min-h-11 items-center font-semibold text-[#08616d] underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-[#087b82]">Start a search</Link>
          </div>
        )}
        {state.searchStatus === "error" && (
          <div role="alert" className="client-card border border-[#efc7c7] p-5">
            <p className="mb-4 text-sm text-[#9d2727]">{state.searchError ?? "Search could not be completed."}</p>
            <button type="button" onClick={() => void runSearch(state.filters)} className="client-primary-button w-full">Try again</button>
          </div>
        )}
        {state.searchStatus === "empty" && (
          <div className="client-card p-6 text-center text-sm">
            <p className="font-semibold text-[#11213b]">No available items matched these details.</p>
            <p className="mt-2 text-[#576078]">Try editing your search details or post a missing-item report.</p>
          </div>
        )}
        {allRejected && (
          <div className="client-card p-6 text-center text-sm">
            <p className="font-semibold text-[#11213b]">You reviewed every possible match.</p>
            <p className="mt-2 text-[#576078]">None was your item. You can post a missing-item report.</p>
          </div>
        )}
        {state.searchStatus === "results" && !allRejected && (
          <section aria-label="Possible matches" className="space-y-3">
            {visible.map((item, index) => <SearchResultCard key={item.id} item={item} bestMatch={index === 0} />)}
          </section>
        )}

        {hasSearch && (
          <section className="client-info-card space-y-4 p-5">
            <div className="flex items-start gap-3">
              <span aria-hidden="true" className="flex size-11 shrink-0 items-center justify-center rounded-full bg-[#d4f3ef] text-[#006a77]"><Icon name="plus" size={27} /></span>
              <div>
                <h2 className="text-lg font-bold leading-tight text-[#11213b]">Item not here yet?</h2>
                <p className="mt-1 text-sm leading-snug text-[#59647b]">Keep SAULI watching for a possible match.</p>
              </div>
            </div>
            <Link href="/missing/report" className="client-secondary-button flex w-full items-center justify-center">Post missing item</Link>
          </section>
        )}
      </main>
    </>
  );
}
