"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import BackButton from "@/app/components/BackButton";
import Button from "@/app/components/Button";
import Icon from "@/app/components/Icon";
import { useClaimant } from "@/hooks/useClaimant";
import type { SearchFilters } from "@/libs/claimant/types";

export default function SearchFilterForm() {
  const { state, runSearch } = useClaimant();
  const [values, setValues] = useState<SearchFilters>(state.filters);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const router = useRouter();

  function set<K extends keyof SearchFilters>(key: K, value: SearchFilters[K]) {
    setValues((current) => ({ ...current, [key]: value }));
    setError(null);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (state.searchDraft.description.trim().length < 4) {
      setError("Add a description before searching.");
      return;
    }
    setPending(true);
    await runSearch(values);
    router.push("/search/results");
  }

  return (
    <main className="sauli-page pb-10">
      <BackButton href="/">Back</BackButton>
      <h1 className="sauli-title mt-0.5">When and where was it last seen?</h1>
      <p className="sauli-subtitle mt-1">Add what you remember to help narrow the search.</p>
      <form onSubmit={(event) => void submit(event)} className="mt-[58px] space-y-5">
        <div><label htmlFor="last-seen-location" className="sauli-label">Where was it last seen?</label><input id="last-seen-location" className="sauli-field" placeholder="e.g. Library, Canteen" value={values.lastSeenLocation} onChange={(event) => set("lastSeenLocation", event.target.value)} /></div>
        <div><label htmlFor="last-seen-at" className="sauli-label">Date &amp; Time last seen</label><input id="last-seen-at" type="datetime-local" className="sauli-field" value={values.lastSeenAt} onChange={(event) => set("lastSeenAt", event.target.value)} /></div>
        {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
        <Button type="submit" disabled={pending} className="w-full gap-2">{pending ? "Searching…" : "Search available items"}<Icon name="search" size={22} /></Button>
      </form>
    </main>
  );
}
