"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import BackButton from "@/app/components/BackButton";
import Button from "@/app/components/Button";
import Icon from "@/app/components/Icon";
import { useClaimant } from "@/hooks/useClaimant";
import type { SearchFilters } from "@/libs/claimant/types";

function SelectField({ id, label, value, placeholder, options, onChange }: { id: string; label: string; value: string; placeholder: string; options: string[]; onChange: (value: string) => void }) {
  return (
    <div>
      <label htmlFor={id} className="sauli-label">{label}</label>
      <div className="relative"><select id={id} value={value} onChange={(event) => onChange(event.target.value)} className="sauli-field appearance-none pr-9"><option value="">{placeholder}</option>{options.map((option) => <option key={option} value={option.toLowerCase()}>{option}</option>)}</select><Icon name="chevronDown" size={17} className="pointer-events-none absolute right-3 top-3" /></div>
    </div>
  );
}

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
      <h1 className="sauli-title mt-0.5">Help us narrow it down</h1>
      <p className="sauli-subtitle mt-1">Add optional details to improve the search ranking.</p>
      <form onSubmit={(event) => void submit(event)} className="mt-[58px] space-y-5">
        <SelectField id="category" label="Item Category" value={values.category} placeholder="Select Category" options={["Wallet", "Electronics", "Keys", "Clothing", "Other"]} onChange={(value) => set("category", value)} />
        <div className="grid grid-cols-2 gap-3">
          <SelectField id="color" label="Primary Color" value={values.color} placeholder="Select Color" options={["Black", "Blue", "Brown", "Gray", "White", "Other"]} onChange={(value) => set("color", value)} />
          <SelectField id="size" label="Size" value={values.size} placeholder="Select Size" options={["Pocket", "Medium", "Large"]} onChange={(value) => set("size", value)} />
        </div>
        <div><label htmlFor="brand" className="sauli-label">Brand or label</label><input id="brand" className="sauli-field" placeholder="e.g. Samsung, Nike" value={values.brand} onChange={(event) => set("brand", event.target.value)} /></div>
        <div><label htmlFor="last-seen-location" className="sauli-label">Where was it last seen?</label><input id="last-seen-location" className="sauli-field" placeholder="e.g. Library, Canteen" value={values.lastSeenLocation} onChange={(event) => set("lastSeenLocation", event.target.value)} /></div>
        <div><label htmlFor="last-seen-at" className="sauli-label">Date &amp; Time last seen</label><input id="last-seen-at" type="datetime-local" className="sauli-field" value={values.lastSeenAt} onChange={(event) => set("lastSeenAt", event.target.value)} /></div>
        {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
        <Button type="submit" disabled={pending} className="w-full gap-2">{pending ? "Searching…" : "Search available items"}<Icon name="search" size={22} /></Button>
      </form>
    </main>
  );
}
