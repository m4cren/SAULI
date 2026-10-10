import AdminIcon from "./AdminIcon";
import { hardwareItems } from "../_data/mockAdminData";

export default function HardwareStatusPanel({ unlockedDoors, onUnlock, onRelock }: { unlockedDoors: readonly string[]; onUnlock: (door: "pocket-door" | "medium-door") => void; onRelock: (door: "pocket-door" | "medium-door") => void }) {
  return <section className="admin-card admin-hardware" aria-labelledby="hardware-heading"><h2 id="hardware-heading">Hardware</h2><p className="admin-card-description">Prototype component status</p>
    <ul>{hardwareItems.map((item) => {
      const isDoor = item.id === "pocket-door" || item.id === "medium-door";
      const unlocked = unlockedDoors.includes(item.id);
      return <li key={item.id}><span className="admin-hardware-icon"><AdminIcon name={item.icon} size={21} /></span><span className="admin-hardware-copy"><strong>{item.name}</strong><small>{item.description}</small><span className="admin-hardware-state">{isDoor ? unlocked ? "Unlocked — simulated" : "Locked — sample state" : "Online — sample state"}</span>{isDoor && <button type="button" className="admin-inline-action" onClick={() => unlocked ? onRelock(item.id) : onUnlock(item.id)}>{unlocked ? "Simulate door closed and locked" : "Admin unlock"}</button>}</span><span className="admin-hardware-indicator" aria-hidden="true" /></li>;
    })}</ul>
  </section>;
}
