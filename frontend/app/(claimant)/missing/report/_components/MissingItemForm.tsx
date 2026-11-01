"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import Button from "@/app/components/Button";
import { useAuth } from "@/hooks/useAuth";
import { useClaimant } from "@/hooks/useClaimant";
import { normalizeNotificationEmail } from "@/libs/claimant/notificationEmail";

function maskedAddress(address: string): string {
  const [local, domain] = address.trim().split("@");
  if (!local || !domain) return "Add an email address";
  return `${local.slice(0, 3)}\u2022\u2022\u2022\u2022\u2022\u2022@${domain}`;
}

export default function MissingItemForm() {
  const { user } = useAuth();
  const { state, postMissingReport } = useClaimant();
  const [email, setEmail] = useState(user?.email ?? "");
  const emailEdited = useRef(false);
  const [editingEmail, setEditingEmail] = useState(!normalizeNotificationEmail(user?.email ?? ""));
  const [emailEnabled, setEmailEnabled] = useState(true);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submitting = useRef(false);
  const router = useRouter();
  const summary = state.searchSummary || state.searchDraft.description.trim();

  useEffect(() => {
    if (!emailEdited.current) {
      setEmail(user?.email ?? "");
    }
  }, [user?.email]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting.current) return;
    if (!state.searchRequestId) { setError("Search for your item before posting a report."); return; }
    const normalized = normalizeNotificationEmail(email);
    if (!normalized) {
      setEditingEmail(true);
      setError("Enter a valid email address for this report.");
      return;
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

  return <>
    <header className="client-hero">
      <div className="client-hero-body">
        <Link href="/search/results" className="client-hero-back"><span aria-hidden="true">←</span>Search results</Link>
        <h1 className="mt-5 text-[clamp(2rem,8vw,3rem)] font-bold leading-[1.08] text-white">Post your missing item</h1>
        <p className="mt-3 max-w-[35ch] text-[16px] leading-relaxed text-white/85">We’ll reuse your search details and notify you when a possible match is found.</p>
      </div>
    </header>
    <main className="client-content client-overlap min-w-0 pb-24">
      <form onSubmit={(event) => void submit(event)} className="flex min-w-0 flex-col gap-6">
        <section className="client-card min-w-0 rounded-[28px] p-5 sm:p-6" aria-labelledby="missing-summary-title">
          <h2 id="missing-summary-title" className="flex items-center gap-2 text-sm font-bold tracking-[0.04em] text-[#075765]">
            <span aria-hidden="true" className="text-2xl leading-none text-[#10b8ab]">✦</span>
            SAULI SUMMARY
          </h2>
          <p className="mt-4 break-words text-[16px] leading-relaxed text-[#252e49]">{summary || "Your search details will appear here."}</p>
          <Link href="/search/filters" className="mt-5 inline-flex min-h-11 items-center text-[16px] font-bold text-[#086276] underline-offset-4 hover:underline focus-visible:rounded focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#0B474F]">Edit search details</Link>
        </section>

        <section aria-labelledby="notification-title" className="min-w-0">
          <h2 id="notification-title" className="client-section-title mb-4">How should we notify you?</h2>
          <div className="client-card min-w-0 rounded-[24px] p-4 sm:p-5">
            <div className="flex min-w-0 items-start gap-3">
              <span aria-hidden="true" className="flex size-12 shrink-0 items-center justify-center rounded-full bg-[#dcf5f2] text-2xl text-[#076279]">✉</span>
              <div className="min-w-0 flex-1">
                <label htmlFor="email-enabled" className="block text-[17px] font-bold text-[#101d39]">Gmail notification</label>
                <p className="mt-1 text-[14px] leading-snug text-[#4d5d75]">We’ll email you when SAULI finds a possible match.</p>
                <p className="mt-3 break-all text-[15px] font-semibold text-[#101d39]">{maskedAddress(email)}</p>
                <button type="button" onClick={() => setEditingEmail(true)} className="mt-1 min-h-10 text-sm font-semibold text-[#086276] underline underline-offset-4 focus-visible:rounded focus-visible:outline-2 focus-visible:outline-[#0B474F]">Change email</button>
              </div>
              <input id="email-enabled" type="checkbox" checked={emailEnabled} onChange={(event) => setEmailEnabled(event.target.checked)} className="mt-1 size-6 shrink-0 accent-[#169f95]" aria-label="Email me when a possible match is found" />
            </div>
            <div className={editingEmail ? "mt-4" : "hidden"}>
              <label htmlFor="notification-email" className="mb-2 block text-sm font-semibold text-[#102c3b]">Email address</label>
              <input id="notification-email" type="email" autoComplete="email" required maxLength={254}
                className="client-field w-full" placeholder="name@example.com" value={email}
                onChange={(event) => { emailEdited.current = true; setEmail(event.target.value); }} />
              {!user?.email && <p className="mt-2 text-sm text-[#526174]">Your sign-in did not provide an email. Enter one to receive match alerts.</p>}
            </div>
          </div>
          <p className="mt-4 flex gap-2 text-sm leading-relaxed text-[#535c73]"><span aria-hidden="true" className="text-lg">ⓘ</span><span>Check your Spam or Promotions folder if a future match alert does not appear. Posting a report does not send an email.</span></p>
        </section>
        {!state.searchRequestId && <p role="status" className="client-info-card p-4 text-sm">
          Search for your item before posting a report. <Link href="/" className="font-semibold underline underline-offset-2">Start a search</Link>
        </p>}
        {error && <p role="alert" className="rounded-xl bg-[#fff1f0] p-3 text-sm text-red-700">{error}</p>}
        <Button type="submit" disabled={pending || !state.searchRequestId} className="client-primary-button mt-2 w-full">{pending ? "Posting…" : emailEnabled ? "Post and notify me" : "Post missing item"}</Button>
      </form>
    </main>
  </>;
}
