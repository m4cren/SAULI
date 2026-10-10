"use client";

import { useMemo, useState } from "react";
import AdminIcon from "./AdminIcon";
import AdminModal from "./AdminModal";
import AdminPageHeader from "./AdminPageHeader";
import { compartmentIds, filterRetrievals, formatManilaDate, retrievalRecords, toCsv } from "../_data/mockAdminData";
import type { RetrievalRecord } from "../_types/admin";

export default function RetrievalLogs() {
  const [search, setSearch] = useState("");
  const [date, setDate] = useState("");
  const [compartment, setCompartment] = useState("");
  const [selected, setSelected] = useState<RetrievalRecord | null>(null);
  const filtered = useMemo(() => filterRetrievals(retrievalRecords, search, date, compartment), [search, date, compartment]);
  const clear = () => { setSearch(""); setDate(""); setCompartment(""); };
  const download = () => {
    const blob = new Blob(["\uFEFF", toCsv(filtered)], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "sauli-retrieval-logs-2026-10-06.csv";
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return <>
    <AdminPageHeader title="Retrieval Logs" description="Review completed item retrievals and verification details." action={<button type="button" className="admin-secondary admin-download" onClick={download}><AdminIcon name="download" size={19} /> Download CSV</button>} />
    <section className="admin-card admin-logs-card" aria-label="Retrieval records">
      <div className="admin-log-filters">
        <label className="admin-search-field"><span className="admin-sr-only">Search retrievals</span><AdminIcon name="search" size={19} /><input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search retriever, item, ID, or compartment" /></label>
        <label className="admin-filter-field"><span>Date</span><input type="date" value={date} onChange={(event) => setDate(event.target.value)} /></label>
        <label className="admin-filter-field"><span>Compartment</span><select value={compartment} onChange={(event) => setCompartment(event.target.value)}><option value="">All compartments</option>{compartmentIds.map((id) => <option key={id} value={id}>{id}</option>)}</select></label>
        <button type="button" className="admin-text-action" onClick={clear} disabled={!search && !date && !compartment}>Clear filters</button>
      </div>
      {filtered.length ? <div className="admin-table-scroll"><table className="admin-logs-table"><thead><tr><th scope="col">Retrieval ID</th><th scope="col">Date &amp; Time</th><th scope="col">Retriever</th><th scope="col">Item</th><th scope="col">Compartment</th><th scope="col">Status</th></tr></thead><tbody>{filtered.map((record) => <tr key={record.id} onClick={() => setSelected(record)}><td><button type="button" className="admin-row-open" onClick={() => setSelected(record)} aria-label={`View details for ${record.id}`}>{record.id}</button></td><td>{formatManilaDate(record.timestamp)}</td><td>{record.retriever}</td><td>{record.item}</td><td>{record.compartment}</td><td><span className="admin-retrieved-badge">{record.status}</span></td></tr>)}</tbody></table></div> : <div className="admin-empty"><AdminIcon name="search" size={32} /><h2>No retrieval records found</h2><p>Try adjusting or clearing the filters.</p><button type="button" className="admin-secondary" onClick={clear}>Clear filters</button></div>}
      <p className="admin-record-count">Showing {filtered.length} of {retrievalRecords.length} prototype records</p>
    </section>
    {selected && <AdminModal title={`Retrieval ${selected.id}`} description="Completed retrieval · prototype record" onClose={() => setSelected(null)}>
      <dl className="admin-detail-list"><div><dt>Retriever</dt><dd>{selected.retriever}</dd></div><div><dt>Item</dt><dd>{selected.item}</dd></div><div><dt>Date and time</dt><dd>{formatManilaDate(selected.timestamp)}</dd></div><div><dt>Compartment</dt><dd>{selected.compartment}</dd></div><div><dt>Door category</dt><dd>{selected.compartment.startsWith("P") ? "Pocket-size" : "Medium-size"}</dd></div><div><dt>Retrieval status</dt><dd>{selected.status}</dd></div><div><dt>Verification result</dt><dd>{selected.verification}</dd></div></dl>
      <button type="button" className="admin-primary admin-modal-done" onClick={() => setSelected(null)}>Done</button>
    </AdminModal>}
  </>;
}
