"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import BackButton from "@/app/components/BackButton";
import Button from "@/app/components/Button";
import { useClaimant } from "@/hooks/useClaimant";

function NotificationToggle({ title, description, checked, onChange }: { title: string; description: string; checked: boolean; onChange: (value: boolean) => void }) {
  return (
    <label className="sauli-card flex min-h-[59px] cursor-pointer items-center justify-between gap-3 p-2.5">
      <span><span className="block text-[12px] font-semibold tracking-[0.06em]">{title}</span><span className="block text-[10px]">{description}</span></span>
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} className="size-5 accent-[#1b9c91]" />
    </label>
  );
}

export default function MissingItemForm() {
  const { state, postMissingReport } = useClaimant();
  const [phone, setPhone] = useState("");
  const [smsEnabled, setSmsEnabled] = useState(true);
  const [inAppEnabled, setInAppEnabled] = useState(true);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();
  const summary = [state.searchDraft.description.trim(), state.filters.lastSeenLocation && `Last seen near ${state.filters.lastSeenLocation}.`, state.filters.brand && `Brand or label: ${state.filters.brand}.`].filter(Boolean).join(" ");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!state.searchDraft.description.trim()) { setError("Start a search before posting a report."); return; }
    if (!smsEnabled && !inAppEnabled) { setError("Choose at least one notification method."); return; }
    if (smsEnabled && phone.replace(/\D/g, "").length < 10) { setError("Enter a valid mobile number for SMS notifications."); return; }
    setPending(true);
    setError(null);
    try {
      await postMissingReport({ phone, smsEnabled, inAppEnabled });
      router.push("/missing/active");
    } catch {
      setError("Could not create the prototype report. Please try again.");
      setPending(false);
    }
  }

  return (
    <main className="sauli-page flex min-h-[calc(100dvh-148px)] flex-col">
      <BackButton href="/search/results">Search Results</BackButton>
      <h1 className="sauli-title mt-1">Post your missing item</h1>
      <p className="sauli-subtitle mt-1">We’ll reuse your search description and filters. Just choose how SAULI should notify you.</p>
      <form onSubmit={(event) => void submit(event)} className="mt-7 flex flex-1 flex-col">
        <div className="sauli-card min-h-[194px] p-2.5"><h2 className="text-[10px] font-bold tracking-[0.05em]">SAULI GENERATED SUMMARY</h2><p className="mt-3 text-[12px] leading-[1.3] tracking-[0.04em]">{summary || "Your search details will appear here."}</p><Link href="/search/filters" className="mt-3 inline-block min-h-11 py-3 text-xs font-bold tracking-[0.1em] text-[#267781] focus-visible:outline-2 focus-visible:outline-[var(--sauli-brand)]">Edit search details</Link></div>
        <p className="mt-2 text-[10px] text-[#666]">Prototype summary based on your search. No notification is sent.</p>
        <div className="mt-4"><label htmlFor="mobile-number" className="sauli-label">Mobile number for SMS</label><input id="mobile-number" type="tel" inputMode="tel" autoComplete="tel" className="sauli-field" placeholder="+639 900 000 0000" value={phone} onChange={(event) => setPhone(event.target.value)} /></div>
        <div className="mt-2 space-y-2"><NotificationToggle title="SMS notification" description="Text me when SAULI finds a possible match." checked={smsEnabled} onChange={setSmsEnabled} /><NotificationToggle title="In-app notification" description="Show the match in my SAULI account." checked={inAppEnabled} onChange={setInAppEnabled} /></div>
        {error && <p role="alert" className="mt-3 text-sm text-red-700">{error}</p>}
        <Button type="submit" disabled={pending} className="mt-auto w-full">{pending ? "Posting…" : "Post and notify me"}</Button>
      </form>
    </main>
  );
}
