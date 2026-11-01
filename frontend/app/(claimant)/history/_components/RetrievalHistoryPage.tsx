"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Icon from "@/app/components/Icon";
import { getClaimantRetrievalHistory } from "@/libs/api/sauli";
import { formatDateTime } from "@/libs/claimant/format";
import type { CompartmentId, RetrievalRecord } from "@/libs/claimant/types";

type Filter = "all" | "month" | "search";

function HistoryCard({ record }: { record: RetrievalRecord }) {
  return <article className="client-card flex min-w-0 items-start gap-4 rounded-[22px] p-4 sm:p-5">
    <span aria-hidden="true" className="mt-2 flex size-11 shrink-0 items-center justify-center rounded-full bg-[#ddf7f4] text-[#159f95]"><Icon name="check" size={25} /></span>
    <div className="min-w-0 flex-1">
      <p className="text-xs font-bold uppercase tracking-[0.07em] text-[#159f95]">Retrieved</p>
      <h2 className="mt-1 break-words text-[17px] font-bold leading-snug text-[#101d39]">{record.itemName}</h2>
      <p className="mt-1 break-words text-sm text-[#647084]">Retriever: {record.retriever}</p>
      <p className="mt-2 text-sm font-semibold text-[#101d39]">{formatDateTime(record.recordedAt)}</p>
    </div>
    <span aria-label={`Compartment ${record.compartmentId}`} className="shrink-0 rounded-lg border border-[#b9e8e7] bg-[#ebf9f8] px-2 py-1 text-sm font-bold text-[#0b4857]">{record.compartmentId}</span>
  </article>;
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
    }).catch(() => {
      if (active) { setHistory([]); setError("Retrieval history is unavailable. Try again."); }
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [retry]);

  const monthFormatter = new Intl.DateTimeFormat("en-PH", { timeZone: "Asia/Manila", year: "numeric", month: "numeric" });
  const nowMonth = monthFormatter.format(new Date());
  const records = [...history]
    .sort((a, b) => Date.parse(b.recordedAt) - Date.parse(a.recordedAt))
    .filter((record) => filter !== "month" || monthFormatter.format(new Date(record.recordedAt)) === nowMonth)
    .filter((record) => filter !== "search" || `${record.itemName} ${record.retriever} ${record.compartmentId}`.toLowerCase().includes(query.trim().toLowerCase()));

  return <>
    <header className="client-hero">
      <div className="client-hero-body">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[#b8fff3]">Audit trail</p>
        <h1 className="mt-3 text-[clamp(2.2rem,9vw,3.2rem)] font-bold leading-[1.08] text-white">Retrieval history</h1>
        <p className="mt-3 max-w-[38ch] text-base leading-relaxed text-white/85">A transparent log of items released from the SAULI container.</p>
      </div>
    </header>
    <main className="client-content client-overlap min-w-0 pb-24">
      <div className="client-card min-w-0 rounded-[28px] p-4 sm:p-5">
        <div role="group" aria-label="Filter retrieval history" className="grid min-w-0 grid-cols-3 gap-2">
          {([['all', 'All records'], ['month', 'This month'], ['search', 'Search']] as const).map(([value, label]) => (
            <button key={value} type="button" aria-pressed={filter === value} onClick={() => setFilter(value)} className={`min-h-11 min-w-0 rounded-full border px-1.5 text-[12px] font-semibold leading-tight focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#0B474F] sm:text-sm ${filter === value ? "sauli-gradient border-transparent text-white" : "border-[#cbe6e5] bg-white text-[#4a5871]"}`}>{value === "search" && <Icon name="search" size={17} className="mr-1 inline-block align-middle" />}{label}</button>
          ))}
        </div>
        {filter === "search" && <div className="mt-4"><label htmlFor="history-query" className="mb-2 block text-sm font-semibold text-[#102d42]">Search retrieval records</label><input id="history-query" type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Item, retriever, or compartment" className="client-field" /></div>}
      </div>

      <div aria-live="polite" className="mt-5 space-y-4">
        {loading && <p role="status" className="client-card rounded-[22px] p-6 text-center text-sm text-[#526174]">Loading retrieval history…</p>}
        {!loading && error && <div role="alert" className="client-card rounded-[22px] p-6 text-sm text-red-700"><p>{error}</p><button type="button" className="mt-2 min-h-11 font-semibold underline underline-offset-4" onClick={() => { setLoading(true); setRetry((value) => value + 1); }}>Retry</button></div>}
        {!loading && !error && records.map((record) => <HistoryCard key={record.id} record={record} />)}
        {!loading && !error && records.length === 0 && <div className="client-card rounded-[22px] p-6 text-center text-sm text-[#526174]">{filter === "all" ? "No retrieval records yet." : "No retrieval records match this filter."}</div>}
      </div>
      <Link href="/missing/reports" className="mt-7 inline-flex min-h-11 items-center text-sm font-semibold text-[#0b5f70] underline underline-offset-4">View missing-item reports</Link>
    </main>
  </>;
}
