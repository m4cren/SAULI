"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import BackButton from "@/app/components/BackButton";
import Button from "@/app/components/Button";
import { useAuth } from "@/hooks/useAuth";
import { useClaimant } from "@/hooks/useClaimant";
import { normalizeNotificationEmail } from "@/libs/claimant/notificationEmail";

export default function MissingItemForm() {
  const { user } = useAuth();
  const { state, postMissingReport } = useClaimant();
  const [email, setEmail] = useState(user?.email ?? "");
  const emailEdited = useRef(false);
  const [emailEnabled, setEmailEnabled] = useState(true);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submitting = useRef(false);
  const router = useRouter();
  const summary = state.searchSummary || state.searchDraft.description.trim();

  useEffect(() => {
    if (!emailEdited.current) setEmail(user?.email ?? "");
  }, [user?.email]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting.current) return;
    if (!state.searchRequestId) { setError("Search for your item before posting a report."); return; }
    const normalized = normalizeNotificationEmail(email);
    if (!normalized) {
      setError("Enter a valid email address for this report."); return;
    }
    submitting.current = true;
    setPending(true);
    setError(null);
    try {
      await postMissingReport({ email: normalized, emailEnabled });
      router.push("/missing/active");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The report could not be posted. Please try again.");
      setPending(false);
      submitting.current = false;
    }
  }

  return <main className="sauli-page flex min-h-[calc(100dvh-148px)] flex-col">
    <BackButton href="/search/results">Search Results</BackButton>
    <h1 className="sauli-title mt-1">Post your missing item</h1>
    <p className="sauli-subtitle mt-1">We’ll reuse your search description and last-seen details. Choose where SAULI should email you.</p>
    <form onSubmit={(event) => void submit(event)} className="mt-7 flex flex-1 flex-col">
      <div className="sauli-card min-h-[194px] p-2.5">
        <h2 className="text-[10px] font-bold tracking-[0.05em]">SAULI GENERATED SUMMARY</h2>
        <p className="mt-3 text-[12px] leading-[1.3] tracking-[0.04em]">{summary || "Your search details will appear here."}</p>
        <Link href="/search/filters" className="mt-3 inline-block min-h-11 py-3 text-xs font-bold tracking-[0.1em] text-[#267781]">Edit search details</Link>
      </div>
      <div className="mt-5">
        <label htmlFor="notification-email" className="sauli-label">Email address</label>
        <input id="notification-email" type="email" autoComplete="email" required maxLength={254}
          className="sauli-field" placeholder="name@example.com" value={email}
          onChange={(event) => { emailEdited.current = true; setEmail(event.target.value); }} />
        {!user?.email && <p className="mt-2 text-xs text-[#555]">Your sign-in did not provide an email. Enter one to receive match alerts.</p>}
      </div>
      <label className="sauli-card mt-3 flex min-h-[64px] cursor-pointer items-center justify-between gap-3 p-3">
        <span><span className="block text-sm font-semibold">Email me when a possible match is found</span>
          <span className="mt-1 block text-xs text-[#555]">You will review and confirm the item in SAULI.</span></span>
        <input type="checkbox" checked={emailEnabled} onChange={(event) => setEmailEnabled(event.target.checked)} className="size-5 accent-[#1b9c91]" />
      </label>
      <p className="mt-3 text-xs text-[#555]">We’ll email you only after a possible match is placed in the container. Posting a report does not send an email.</p>
      {error && <p role="alert" className="mt-3 text-sm text-red-700">{error}</p>}
      <Button type="submit" disabled={pending || !state.searchRequestId} className="mt-auto w-full">{pending ? "Posting…" : "Post missing item"}</Button>
    </form>
  </main>;
}
