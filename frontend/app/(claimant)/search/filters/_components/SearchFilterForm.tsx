"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import Button from "@/app/components/Button";
import Icon from "@/app/components/Icon";
import ClientHero from "@/app/components/ClientHero";
import { useClaimant } from "@/hooks/useClaimant";
import type { SearchFilters } from "@/libs/claimant/types";

export default function SearchFilterForm() {
  const { state, setFilters, runSearch } = useClaimant();
  const [values, setValues] = useState<SearchFilters>(state.filters);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const router = useRouter();
  const [lastSeenDate, selectedTime] = values.lastSeenAt.split("T");
  const lastSeenTime = selectedTime || "00:00";

  function set<K extends keyof SearchFilters>(key: K, value: SearchFilters[K]) {
    const updated = { ...values, [key]: value };
    setValues(updated);
    setFilters(updated);
    setError(null);
  }

  function setLastSeenAt(date: string, time: string) {
    set("lastSeenAt", date ? `${date}T${time || "00:00"}` : "");
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (state.searchDraft.description.trim().length < 4) {
      setError("Add a description before searching.");
      return;
    }
    if (values.lastSeenAt) {
      const lastSeen = new Date(values.lastSeenAt).getTime();
      if (!Number.isFinite(lastSeen) || lastSeen > Date.now()) {
        setError("Last seen cannot be in the future. Choose an earlier date and time.");
        return;
      }
    }
    setPending(true);
    await runSearch(values);
    router.push("/search/results");
  }

  return (
    <>
      <ClientHero backHref="/" backLabel="Back" title="Help us narrow it down" subtitle="Just tell us where and roughly when you last saw it." />
      <main className="client-content client-overlap">
        <form onSubmit={(event) => void submit(event)} className="client-card space-y-6 p-5">
          <p className="flex items-center gap-2 text-[16px] font-bold text-[#0b747a]"><span aria-hidden="true" className="text-2xl">✦</span>2 quick details</p>
          <div><label htmlFor="last-seen-location" className="mb-2 block text-[17px] font-semibold text-[#0b2f3a]">Where did you last see it?</label><input id="last-seen-location" className="client-field" placeholder="e.g. Library, canteen, Room 204" value={values.lastSeenLocation} onChange={(event) => set("lastSeenLocation", event.target.value)} /></div>
          <fieldset className="min-w-0">
            <legend className="mb-2 text-[17px] font-semibold text-[#0b2f3a]">When did you last see it?</legend>
            <label htmlFor="last-seen-date" className="mb-1 block text-sm font-medium text-[#35545d]">Date</label>
            <div className="relative">
              <input id="last-seen-date" type="date" className="client-field min-w-0" value={lastSeenDate} aria-describedby="last-seen-help" onChange={(event) => setLastSeenAt(event.target.value, lastSeenTime)} />
              {!lastSeenDate && <span aria-hidden="true" className="pointer-events-none absolute inset-y-px right-10 left-px flex items-center rounded-l-[11px] bg-white pl-4 text-[#82929d]">Choose a date</span>}
            </div>
            {lastSeenDate && <div className="mt-3">
              <label htmlFor="last-seen-time" className="mb-1 block text-sm font-medium text-[#35545d]">Time</label>
              <input id="last-seen-time" type="time" className="client-field min-w-0" value={lastSeenTime} onChange={(event) => setLastSeenAt(lastSeenDate, event.target.value)} />
            </div>}
            <p id="last-seen-help" className="mt-2 text-xs text-[#6a8088]">An approximate date and time is okay. Leave the time at midnight if you only know the date.</p>
          </fieldset>
          {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
          <Button type="submit" disabled={pending} className="client-primary-button w-full gap-2">{pending ? "Searching…" : "Search stored items"}<Icon name="search" size={22} /></Button>
        </form>
        <aside className="client-info-card mt-5 flex items-start gap-3 p-4"><span aria-hidden="true" className="flex size-10 shrink-0 items-center justify-center rounded-full bg-white text-[#0b8080]"><Icon name="lightbulb" size={28} /></span><span><strong className="block text-[16px] text-[#0b474f]">Why these details matter</strong><span className="text-sm text-[#4f6974]">Location and time help SAULI find the closest match.</span></span></aside>
      </main>
    </>
  );
}
