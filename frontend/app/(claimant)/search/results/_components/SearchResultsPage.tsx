"use client";

import Link from "next/link";
import BackButton from "@/app/components/BackButton";
import Button from "@/app/components/Button";
import Icon from "@/app/components/Icon";
import { useClaimant } from "@/hooks/useClaimant";
import SearchResultCard from "./SearchResultCard";

export default function SearchResultsPage() {
  const { state, runSearch } = useClaimant();
  const visible = state.searchResults.filter((item) => !state.rejectedCandidateIds.includes(item.id));
  const allRejected = state.searchStatus === "results" && state.searchResults.length > 0 && visible.length === 0;

  return (
    <main className="sauli-page pb-10">
      <BackButton href="/">New search</BackButton>
      <h1 className="sauli-title mt-0.5">Search results</h1>
      <p aria-live="polite" className="sauli-subtitle mt-1">{state.searchStatus === "results" ? `${visible.length} possible ${visible.length === 1 ? "match" : "matches"}` : "Find your missing item"}</p>
      <div className="sauli-card mt-6 flex min-h-11 items-center justify-between gap-3 px-2.5">
        <span className="min-w-0 truncate text-sm tracking-[0.04em]">{state.searchDraft.description || "No search description yet"}</span>
        <Link href="/search/filters" className="min-h-11 shrink-0 px-2 py-3 text-sm font-semibold focus-visible:outline-2 focus-visible:outline-[var(--sauli-brand)]">Edit</Link>
      </div>

      {state.searchStatus === "searching" && <div role="status" className="mt-5 rounded-lg bg-white p-6 text-center text-sm">Searching available items…</div>}
      {state.searchStatus === "idle" && <div className="mt-5 rounded-lg bg-white p-6 text-center"><p className="mb-4 text-sm">Start with a description to find possible matches.</p><Link href="/" className="font-semibold text-[var(--sauli-brand)]">Start a search</Link></div>}
      {state.searchStatus === "error" && <div role="alert" className="mt-5 rounded-lg border border-red-200 bg-white p-5"><p className="mb-3 text-sm">{state.searchError ?? "Search could not be completed."}</p><Button type="button" onClick={() => void runSearch(state.filters)} className="w-full">Try again</Button></div>}
      {state.searchStatus === "empty" && <div className="mt-5 rounded-lg bg-white p-6 text-center text-sm"><p className="font-semibold">No available items matched these details.</p><p className="mt-2 text-[#666]">Try editing your filters or post a missing-item report.</p></div>}
      {allRejected && <div className="mt-5 rounded-lg bg-white p-6 text-center text-sm"><p className="font-semibold">You reviewed every possible match.</p><p className="mt-2 text-[#666]">None was your item. You can post a missing-item report.</p></div>}
      {state.searchStatus === "results" && !allRejected && <div className="mt-1 space-y-1.5">{visible.map((item) => <SearchResultCard key={item.id} item={item} />)}</div>}

      {(state.searchStatus === "results" || state.searchStatus === "empty") && (
        <section className="mt-6 rounded-[11px] border border-dashed border-[#a8a8a8] p-3.5">
          <div className="flex gap-3"><Icon name="plus" size={30} /><div><h2 className="text-[15px] font-medium">Item not here yet?</h2><p className="mt-1 text-[13px] leading-snug text-[#666]">You can leave a prototype missing-item report while monitoring is being developed.</p></div></div>
          <Link href="/missing/report" className="mt-3 flex min-h-11 items-center justify-center rounded-md border border-[var(--sauli-brand)] bg-white text-sm font-semibold text-[var(--sauli-brand)] focus-visible:outline-2 focus-visible:outline-[var(--sauli-brand)]">Post missing item</Link>
        </section>
      )}
    </main>
  );
}
