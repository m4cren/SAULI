"use client";

import { useCallback, useEffect, useState } from "react";
import { addKioskDevice, approveKioskPairing, changeUnitStatus, createSauliUnit, editSauliUnit, getUnitFleet, revokeKioskDevice, type SauliUnit } from "@/libs/api/sauli";
import AdminPageHeader from "../../_components/AdminPageHeader";

function connectivity(status: SauliUnit["devices"][number]["status"], lastSeen: string | null): string {
  if (status !== "active") return "Offline";
  if (!lastSeen) return "Never connected";
  const age = Date.now() - Date.parse(lastSeen);
  return age >= 0 && age < 90_000 ? "Online" : "Offline";
}

export default function UnitFleet() {
  const [units, setUnits] = useState<SauliUnit[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [pairing, setPairing] = useState<{ code: string; expires: string } | null>(null);
  const [unitForm, setUnitForm] = useState({ unit_code: "", display_name: "", campus_code: "", campus_name: "", building_name: "", floor: "", location_description: "" });
  const [deviceForm, setDeviceForm] = useState({ unit_id: "", device_code: "", hostname: "", hardware_type: "Raspberry Pi 4 Model B, 4GB" });
  const [editingUnitId, setEditingUnitId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState({ display_name: "", campus_code: "", campus_name: "", building_name: "", floor: "", location_description: "" });
  const refresh = useCallback(async () => { try { setUnits(await getUnitFleet()); setError(""); } catch (cause) { setError(cause instanceof Error ? cause.message : "Fleet unavailable."); } }, []);
  useEffect(() => {
    const initial = window.setTimeout(() => { void refresh(); }, 0);
    const interval = window.setInterval(() => { void refresh(); }, 15000);
    return () => { window.clearTimeout(initial); window.clearInterval(interval); };
  }, [refresh]);

  async function run(action: () => Promise<unknown>) {
    setBusy(true); setError("");
    try { await action(); await refresh(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Operation failed."); }
    finally { setBusy(false); }
  }

  return <>
    <AdminPageHeader title="SAULI Units" description="Register cabinets, review capacity, and approve each physical kiosk device." />
    {error && <p role="alert" className="mb-4 rounded-lg border border-red-300 p-3 text-red-700">{error}</p>}
    <div className="mb-5 grid gap-4 xl:grid-cols-2">
      <form className="admin-card grid gap-3 p-5" onSubmit={(event) => { event.preventDefault(); void run(async () => { await createSauliUnit({ ...unitForm, floor: unitForm.floor || null, location_description: unitForm.location_description || null }); setUnitForm({ unit_code: "", display_name: "", campus_code: "", campus_name: "", building_name: "", floor: "", location_description: "" }); }); }}>
        <h2>Register a unit</h2>
        {(["unit_code", "display_name", "campus_code", "campus_name", "building_name", "floor", "location_description"] as const).map((name) => <label key={name} className="grid gap-1 text-sm"><span>{name.replaceAll("_", " ")}</span><input className="rounded-lg border p-2" value={unitForm[name]} required={!(["floor", "location_description"] as string[]).includes(name)} onChange={(event) => setUnitForm({ ...unitForm, [name]: event.target.value })} /></label>)}
        <button className="admin-primary" disabled={busy}>Create 12 compartments</button>
      </form>
      <form className="admin-card grid content-start gap-3 p-5" onSubmit={(event) => { event.preventDefault(); void run(async () => { await addKioskDevice(deviceForm.unit_id, deviceForm.device_code, deviceForm.hostname, deviceForm.hardware_type); setDeviceForm({ ...deviceForm, device_code: "", hostname: "" }); }); }}>
        <h2>Register a kiosk device</h2>
        <label className="grid gap-1 text-sm">Unit<select className="rounded-lg border p-2" required value={deviceForm.unit_id} onChange={(event) => setDeviceForm({ ...deviceForm, unit_id: event.target.value })}><option value="">Select a unit</option>{units.map((unit) => <option key={unit.id} value={unit.id}>{unit.unit_code}</option>)}</select></label>
        {(["device_code", "hostname", "hardware_type"] as const).map((name) => <label key={name} className="grid gap-1 text-sm"><span>{name.replaceAll("_", " ")}</span><input className="rounded-lg border p-2" value={deviceForm[name]} required={name !== "hostname"} onChange={(event) => setDeviceForm({ ...deviceForm, [name]: event.target.value })} /></label>)}
        <button className="admin-primary" disabled={busy}>Register device</button>
      </form>
    </div>
    {pairing && <div role="status" className="admin-card mb-5 border-amber-400 p-4"><strong>One-time pairing code — expires {new Date(pairing.expires).toLocaleString()}</strong><p className="my-2 break-all font-mono text-sm">{pairing.code}</p><p>Transfer this code to the Pi operator securely. It will not be shown again.</p><button type="button" className="admin-secondary mt-3" onClick={() => setPairing(null)}>Dismiss</button></div>}
    <div className="grid gap-4">{units.map((unit) => <section className="admin-card p-5" key={unit.id}>
      <div className="flex flex-wrap items-start justify-between gap-3"><div><h2>{unit.display_name}</h2><p className="text-sm text-slate-600">{unit.unit_code} · {unit.campus_name}, {unit.building_name}{unit.floor ? `, ${unit.floor}` : ""}</p></div><label className="grid gap-1 text-sm">Administrative status<select className="rounded-lg border p-2" value={unit.status} disabled={busy} onChange={(event) => void run(() => changeUnitStatus(unit.id, event.target.value as SauliUnit["status"]))}>{["provisioning", "active", "maintenance", "inactive", "retired"].map((status) => <option key={status}>{status}</option>)}</select></label></div>
      <p className="my-3 text-sm">{unit.capacity.available} available · {unit.capacity.reserved} reserved · {unit.capacity.occupied} occupied · {unit.capacity.out_of_service} out of service · {unit.capacity.total} active positions</p>
      <button type="button" className="admin-secondary mb-3" disabled={busy} onClick={() => {
        if (editingUnitId === unit.id) { setEditingUnitId(null); return; }
        setEditForm({ display_name: unit.display_name, campus_code: unit.campus_code, campus_name: unit.campus_name, building_name: unit.building_name, floor: unit.floor || "", location_description: unit.location_description || "" });
        setEditingUnitId(unit.id);
      }}>{editingUnitId === unit.id ? "Cancel edit" : "Edit location"}</button>
      {editingUnitId === unit.id && <form className="mb-4 grid gap-3 rounded-lg border p-4 md:grid-cols-2" onSubmit={(event) => { event.preventDefault(); void run(async () => {
        await editSauliUnit(unit.id, { ...editForm, floor: editForm.floor || null, location_description: editForm.location_description || null });
        setEditingUnitId(null);
      }); }}>
        {(["display_name", "campus_code", "campus_name", "building_name", "floor", "location_description"] as const).map((name) => <label key={name} className="grid gap-1 text-sm"><span>{name.replaceAll("_", " ")}</span><input className="rounded-lg border p-2" value={editForm[name]} required={name !== "floor" && name !== "location_description"} onChange={(event) => setEditForm({ ...editForm, [name]: event.target.value })} /></label>)}
        <p className="text-sm text-slate-600 md:col-span-2">Unit code {unit.unit_code} is permanent. Location changes appear to claimants after they refresh.</p>
        <button className="admin-primary md:col-span-2" disabled={busy}>Save unit details</button>
      </form>}
      <div className="grid gap-2">{unit.devices.map((device) => <div key={device.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border p-3 text-sm"><div><strong>{device.device_code}</strong> · {device.status} · {connectivity(device.status, device.last_seen_at)}<p className="text-slate-600">{device.hostname || "No hostname"} · {device.last_seen_at ? `Last seen ${new Date(device.last_seen_at).toLocaleString()}` : "Never connected"}</p></div><div className="flex gap-2">{device.status === "pending" && <button type="button" className="admin-primary" disabled={busy} onClick={() => void run(async () => { const result = await approveKioskPairing(device.id); setPairing({ code: result.pairing_code, expires: result.expires_at }); })}>Approve pairing</button>}{device.status !== "revoked" && <button type="button" className="admin-secondary" disabled={busy} onClick={() => { if (window.confirm(`Revoke ${device.device_code}? Its kiosk sessions will end immediately.`)) void run(() => revokeKioskDevice(device.id)); }}>Revoke</button>}</div></div>)}</div>
    </section>)}</div>
  </>;
}
