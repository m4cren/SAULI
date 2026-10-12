import type { CompartmentId, RetrievalRecord } from "../_types/admin";

export const retrievalRecords: RetrievalRecord[] = [
  ["R-1087", "2026-09-09T12:44:00+08:00", "Angela Lim", "Brown coin purse", "P-04"],
  ["R-1086", "2026-09-09T11:18:00+08:00", "Paolo Cruz", "Black wallet", "P-07"],
  ["R-1085", "2026-09-08T16:32:00+08:00", "Maria Santos", "Blue water bottle", "M-02"],
  ["R-1084", "2026-09-08T14:06:00+08:00", "John Reyes", "Keychain", "P-06"],
  ["R-1083", "2026-09-07T15:51:00+08:00", "Ana Garcia", "Mobile phone", "P-03"],
  ["R-1082", "2026-09-07T10:23:00+08:00", "Carlo Mendoza", "Pencil case", "M-04"],
  ["R-1081", "2026-09-06T13:40:00+08:00", "Bea Torres", "Wristwatch", "P-02"],
  ["R-1080", "2026-09-05T09:16:00+08:00", "Miguel Ramos", "Eyeglass case", "M-01"],
].map(([id, timestamp, retriever, item, compartment]) => ({ id, timestamp, retriever, item, compartment: compartment as CompartmentId, status: "Retrieved", verification: "QR code verified", completionSource: "Web simulation" }));

export const prototypeFootageArchive = { camera: "front", date: "2026-09-08", start: "15:30" } as const;
export function hasPrototypeFootage(camera: string, date: string, start: string) {
  return camera === prototypeFootageArchive.camera && date === prototypeFootageArchive.date && start === prototypeFootageArchive.start;
}

export const hardwareItems = [
  { id: "pocket-door", name: "Pocket-size Door", description: "Main access door for compartments P-01 through P-10.", icon: "door" },
  { id: "medium-door", name: "Medium-size Door", description: "Main access door for compartments M-01 through M-05.", icon: "door" },
  { id: "pi", name: "Raspberry Pi", description: "Kiosk gateway, interface, QR scanner, and main hardware controller. Controls both locks and door reed switches.", icon: "computer" },
  { id: "esp-pocket", name: "ESP32-S3", description: "Monitors load cells for P-01 through P-10.", icon: "chip" },
  { id: "esp-medium", name: "ESP32-S3", description: "Monitors load cells for M-01 through M-05.", icon: "chip" },
  { id: "camera", name: "Raspberry Pi Camera", description: "Captures found-item images and scans retrieval QR codes.", icon: "camera" },
  { id: "display", name: "Touch Display", description: "Seven-inch kiosk touchscreen interface.", icon: "display" },
  { id: "light", name: "Scanning LED Light", description: "Provides consistent lighting during item-image capture.", icon: "light" },
] as const;

export function formatManilaDate(timestamp: string, options: Intl.DateTimeFormatOptions = {}) {
  const value = new Date(timestamp);
  const day = new Intl.DateTimeFormat("en-PH", { timeZone: "Asia/Manila", month: options.month ?? "short", day: "numeric", year: "numeric" }).format(value);
  const time = new Intl.DateTimeFormat("en-PH", { timeZone: "Asia/Manila", hour: "numeric", minute: "2-digit", hour12: true }).format(value);
  return `${day} · ${time}`;
}

export function manilaDateKey(timestamp: string) {
  const parts = new Intl.DateTimeFormat("en-US", { timeZone: "Asia/Manila", year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(new Date(timestamp));
  const value = (type: string) => parts.find((part) => part.type === type)?.value ?? "";
  return `${value("year")}-${value("month")}-${value("day")}`;
}

export function filterRetrievals(records: readonly RetrievalRecord[], search: string, date: string, compartment: string) {
  const query = search.trim().toLocaleLowerCase();
  return records.filter((record) =>
    (!query || [record.id, record.retriever, record.item, record.compartment].some((value) => value.toLocaleLowerCase().includes(query))) &&
    (!date || manilaDateKey(record.timestamp) === date) &&
    (!compartment || record.compartment === compartment)
  );
}

export function toCsv(records: readonly RetrievalRecord[]) {
  const quote = (value: string) => `"${value.replaceAll('"', '""')}"`;
  return ["Retrieval ID,Date and Time,Retriever,Item,Compartment,Status,Completion Source", ...records.map((record) =>
    [record.id, formatManilaDate(record.timestamp), record.retriever, record.item, record.compartment, record.status, record.completionSource].map(quote).join(",")
  )].join("\r\n");
}
