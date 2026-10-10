import type { Compartment } from "../_types/admin";

export default function CompartmentGrid({ compartments, onSelect }: { compartments: readonly Compartment[]; onSelect: (item: Compartment) => void }) {
  const pocket = compartments.filter((item) => item.size === "Pocket-size");
  const medium = compartments.filter((item) => item.size === "Medium-size");
  const button = (item: Compartment) => <button key={item.id} type="button" className={`admin-compartment ${item.status} ${item.sensor}`} onClick={() => onSelect(item)} aria-label={`${item.id}, ${item.status}, sensor ${item.sensor.replace("_", " ")}`} title={`${item.id} · ${item.status} · sensor ${item.sensor.replace("_", " ")}`}>
    {item.id}{item.sensor !== "active" && <span className="admin-compartment-alert" aria-hidden="true">!</span>}
  </button>;
  return <section className="admin-card admin-grid-card" aria-labelledby="compartments-heading">
    <h2 id="compartments-heading">Compartment status</h2><p className="admin-card-description">Select a compartment to inspect its sensor reading.</p>
    <div className="admin-grid-sections"><div><h3>Pocket-size</h3><div className="admin-pocket-grid">{pocket.map(button)}</div></div><div><h3>Medium-size</h3><div className="admin-medium-grid">{medium.map(button)}</div></div></div>
    <div className="admin-legend"><span><i className="admin-dot available" />Available</span><span><i className="admin-dot occupied" />Occupied</span><span><i className="admin-dot attention" />Needs attention</span><span><i className="admin-dot disconnected" />Disconnected</span></div>
  </section>;
}
