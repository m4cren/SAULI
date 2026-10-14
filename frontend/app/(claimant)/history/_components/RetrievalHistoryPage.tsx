"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Icon from "@/app/components/Icon";
import { getClaimantRetrievalHistory } from "@/libs/api/sauli";
import { formatDateTime } from "@/libs/claimant/format";
import type { CompartmentId, RetrievalRecord } from "@/libs/claimant/types";

type Filter = "all" | "month" | "search";

function HistoryCard({ record }: { record: RetrievalRecord }) {
  return (
    <article className="sauli-card flex min-h-[106px] items-center gap-3 p-3.5">
      <div className="flex size-[31px] shrink-0 items-center justify-center rounded-full bg-[#d1d8d7] text-[#33a373]"><Icon name="check" size={19} /></div>
      <div className="min-w-0 flex-1">
        <p className="text-[10px] font-bold tracking-[0.06em] text-[#287981]">RETRIEVED</p>
        <h2 className="mt-1 truncate text-[16px] tracking-[0.1em]">{record.itemName}</h2>
        <p className="text-[10px] tracking-[0.04em] text-[#555]">Retriever: {record.retriever}</p>
        <p className="mt-2 text-[10px] font-semibold">{formatDateTime(record.recordedAt)}</p>
      </div>
      <span aria-label={`Compartment ${record.compartmentId}`} className="self-start rounded border border-[#ccc] px-1 text-[10px] font-semibold">{record.compartmentId}</span>
    </article>
  );
}

export default function RetrievalHistoryPage() {
  const [history, setHistory] = useState<RetrievalRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");
  useEffect(() => {
    let active = true;
    void getClaimantRetrievalHistory().then((rows) => {
      if (!active) return;
      setHistory(rows.map((row) => ({ id: row.id, itemName: row.item_summary,
        compartmentId: row.slot_code as CompartmentId, retriever: row.retriever, recordedAt: row.retrieved_at })));
      setError(null);
    }).catch((cause) => {
      if (active) setError(cause instanceof Error ? cause.message : "Retrieval history is unavailable.");
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [retry]);
  const nowMonth = new Intl.DateTimeFormat("en-PH", { timeZone: "Asia/Manila", year: "numeric", month: "numeric" }).format(new Date());
  const monthOf = (iso: string) => new Intl.DateTimeFormat("en-PH", { timeZone: "Asia/Manila", year: "numeric", month: "numeric" }).format(new Date(iso));
  const records = [...history]
    .sort((a, b) => Date.parse(b.recordedAt) - Date.parse(a.recordedAt))
    .filter((record) => filter !== "month" || monthOf(record.recordedAt) === nowMonth)
    .filter((record) => filter !== "search" || `${record.itemName} ${record.retriever} ${record.compartmentId}`.toLowerCase().includes(query.trim().toLowerCase()));

  return (
    <main className="sauli-page pb-10">
      <p className="sauli-eyebrow mt-1">Audit Trail</p>
      <h1 className="sauli-title mt-3">Retrieval history</h1>
      <p className="sauli-subtitle mt-1">A transparent log of items released from the SAULI container.</p>
      <Link href="/missing/reports" className="mt-2 inline-flex min-h-11 items-center text-sm font-semibold text-[#0B474F] underline">View missing-item reports</Link>
      <div role="group" aria-label="Filter retrieval history" className="mt-7 flex gap-1.5">
        {([["all", "All records"], ["month", "This month"], ["search", "Search"]] as const).map(([value, label]) => (
          <button key={value} type="button" aria-pressed={filter === value} onClick={() => setFilter(value)} className={`min-h-11 flex-1 rounded-full border px-2 text-[11px] tracking-[0.04em] focus-visible:outline-2 focus-visible:outline-[var(--sauli-brand)] ${filter === value ? "sauli-gradient border-transparent font-semibold text-white" : "border-[var(--sauli-border)] bg-white text-[#444]"}`}>{label}</button>
        ))}
      </div>
      {filter === "search" && <div className="mt-3"><label htmlFor="history-query" className="sr-only">Search retrieval records</label><input id="history-query" type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Item, retriever, or compartment" className="sauli-field" /></div>}
      {error && <p role="alert" className="mt-4 text-sm text-red-700">{error} <button type="button" className="underline" onClick={() => { setLoading(true); setRetry((value) => value + 1); }}>Retry</button></p>}
      <div aria-live="polite" className="mt-5 space-y-2.5">
        {loading && <p role="status" className="sauli-card p-6 text-center text-sm">Loading retrieval history…</p>}
        {records.map((record) => <HistoryCard key={record.id} record={record} />)}
        {!loading && !error && records.length === 0 && <div className="sauli-card p-6 text-center text-sm text-[#555]">No retrieval records found.</div>}
      </div>
      <p className="mt-4 text-center text-[10px] text-[#777]">Completed retrievals recorded by SAULI.</p>
    </main>
  );
}
