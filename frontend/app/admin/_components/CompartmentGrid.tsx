import type { StorageSlot } from "@/libs/api/sauli";

export default function CompartmentGrid({ compartments, onSelect }: { compartments: readonly StorageSlot[]; onSelect: (item: StorageSlot) => void }) {
  const pocket = compartments.filter((item) => item.size_class === "pocket");
  const medium = compartments.filter((item) => item.size_class === "medium");
  const button = (item: StorageSlot) => <button key={item.id} type="button" className={`admin-compartment ${item.status}`} onClick={() => onSelect(item)} aria-label={`${item.code}, ${item.status}`} title={`${item.code} · ${item.status}`}>{item.code}</button>;
  return <section className="admin-card admin-grid-card" aria-labelledby="compartments-heading"><h2 id="compartments-heading">Compartment status</h2><p className="admin-card-description">Select a compartment to inspect its stored assignment.</p><div className="admin-grid-sections"><div><h3>Pocket-size</h3><div className="admin-pocket-grid">{pocket.map(button)}</div></div><div><h3>Medium-size</h3><div className="admin-medium-grid">{medium.map(button)}</div></div></div><div className="admin-legend"><span><i className="admin-dot available" />Available</span><span><i className="admin-dot reserved" />Reserved</span><span><i className="admin-dot occupied" />Occupied</span><span><i className="admin-dot out_of_service" />Out of service</span></div></section>;
}
