"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { getRetrievalLogs } from "@/libs/api/sauli";
import { slotCodes as compartmentIds } from "@/libs/storage/slots";
import { filterRetrievals, formatManilaDate, toCsv } from "../_data/mockAdminData";
import type { RetrievalRecord } from "../_types/admin";
import AdminIcon from "./AdminIcon";
import AdminModal from "./AdminModal";
import AdminPageHeader from "./AdminPageHeader";

export default function RetrievalLogs() {
  const [records, setRecords] = useState<RetrievalRecord[]>([]);
  const [search, setSearch] = useState("");
  const [date, setDate] = useState("");
  const [compartment, setCompartment] = useState("");
  const [selected, setSelected] = useState<RetrievalRecord | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const filtered = useMemo(() => filterRetrievals(records, search, date, compartment), [records, search, date, compartment]);
  const refresh = useCallback(async () => {
    try {
      const rows = await getRetrievalLogs();
      setRecords(rows.map((row) => ({ id: row.id, timestamp: row.retrieved_at, retriever: row.retriever,
        item: row.item_summary, compartment: row.slot_code as RetrievalRecord["compartment"],
        status: "Retrieved", verification: "QR code verified",
        completionSource: row.completion_source === "web_simulation" ? "Web simulation" : row.completion_source })));
      setError(null);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Retrieval logs are unavailable."); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => {
    const initial = window.setTimeout(() => { void refresh(); }, 0);
    const interval = window.setInterval(() => { void refresh(); }, 5000);
    const focus = () => { void refresh(); };
    const channel = typeof BroadcastChannel !== "undefined" ? new BroadcastChannel("sauli-storage-slots") : null;
    if (channel) channel.onmessage = () => { void refresh(); };
    window.addEventListener("focus", focus);
    return () => { window.clearTimeout(initial); window.clearInterval(interval); window.removeEventListener("focus", focus); channel?.close(); };
  }, [refresh]);

  function download() {
    const blob = new Blob(["\uFEFF", toCsv(filtered)], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url; anchor.download = "sauli-retrieval-logs.csv";
    document.body.append(anchor); anchor.click(); anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  const clear = () => { setSearch(""); setDate(""); setCompartment(""); };
  return <>
    <AdminPageHeader title="Retrieval Logs" description="Review completed item retrievals and verification details." action={<button type="button" className="admin-secondary admin-download" onClick={download} disabled={!filtered.length}><AdminIcon name="download" size={19} /> Download CSV</button>} />
    <section className="admin-card admin-logs-card" aria-label="Retrieval records">
      <div className="admin-log-filters">
        <label className="admin-search-field"><span className="admin-sr-only">Search retrievals</span><AdminIcon name="search" size={19} /><input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search retriever, item, ID, or compartment" /></label>
        <label className="admin-filter-field"><span>Date</span><input type="date" value={date} onChange={(event) => setDate(event.target.value)} /></label>
        <label className="admin-filter-field"><span>Compartment</span><select value={compartment} onChange={(event) => setCompartment(event.target.value)}><option value="">All compartments</option>{compartmentIds.map((id) => <option key={id} value={id}>{id}</option>)}</select></label>
        <button type="button" className="admin-text-action" onClick={clear} disabled={!search && !date && !compartment}>Clear filters</button>
      </div>
      {error && <p role="alert" className="m-4 text-sm text-red-700">{error} <button type="button" onClick={() => void refresh()} className="underline">Retry</button></p>}
      {loading ? <p role="status" className="m-4 text-sm">Loading retrieval records…</p> : filtered.length ?
        <div className="admin-table-scroll"><table className="admin-logs-table"><thead><tr><th scope="col">Retrieval ID</th><th scope="col">Date &amp; Time</th><th scope="col">Retriever</th><th scope="col">Item</th><th scope="col">Compartment</th><th scope="col">Source</th></tr></thead><tbody>
          {filtered.map((record) => <tr key={record.id}><td><button type="button" className="admin-row-open" onClick={() => setSelected(record)} aria-label={`View details for ${record.id}`}>{record.id.slice(0, 8)}</button></td><td>{formatManilaDate(record.timestamp)}</td><td>{record.retriever}</td><td>{record.item}</td><td>{record.compartment}</td><td>{record.completionSource}</td></tr>)}
        </tbody></table></div> : <div className="admin-empty"><AdminIcon name="search" size={32} /><h2>No retrieval records found</h2><p>{records.length ? "Try adjusting or clearing the filters." : "Completed retrievals will appear here."}</p></div>}
      <p className="admin-record-count">Showing {filtered.length} of {records.length} completed records</p>
    </section>
    {selected && <AdminModal title={`Retrieval ${selected.id.slice(0, 8)}`} description="Completed retrieval" onClose={() => setSelected(null)}>
      <dl className="admin-detail-list"><div><dt>Retriever</dt><dd>{selected.retriever}</dd></div><div><dt>Item</dt><dd>{selected.item}</dd></div><div><dt>Date and time</dt><dd>{formatManilaDate(selected.timestamp)}</dd></div><div><dt>Compartment</dt><dd>{selected.compartment}</dd></div><div><dt>Completion source</dt><dd>{selected.completionSource}</dd></div></dl>
      <button type="button" className="admin-primary admin-modal-done" onClick={() => setSelected(null)}>Done</button>
    </AdminModal>}
  </>;
}
