import type { Compartment, CompartmentId, RetrievalRecord, UnrecognizedCapture } from "../_types/admin";

const pocketIds = Array.from({ length: 10 }, (_, i) => `P-${String(i + 1).padStart(2, "0")}` as CompartmentId);
const mediumIds = Array.from({ length: 5 }, (_, i) => `M-${String(i + 1).padStart(2, "0")}` as CompartmentId);
export const compartmentIds = [...pocketIds, ...mediumIds];

const occupied: Partial<Record<CompartmentId, [string, number, string]>> = {
  "P-01": ["Keychain", 42, "Yesterday · 3:28 PM"],
  "P-02": ["Wristwatch", 62, "Yesterday · 11:05 AM"],
  "P-03": ["Mobile phone", 86, "Today · 9:06 AM"],
  "P-06": ["Wallet", 74, "Today · 8:43 AM"],
  "P-08": ["Coin purse", 55, "Yesterday · 4:18 PM"],
  "P-09": ["Eyeglasses", 39, "Yesterday · 1:13 PM"],
  "M-01": ["Water bottle", 310, "Today · 7:50 AM"],
  "M-03": ["Pencil case", 120, "Yesterday · 10:40 AM"],
  "M-04": ["Umbrella", 415, "Yesterday · 9:15 AM"],
};

export const compartments: Compartment[] = compartmentIds.map((id) => {
  const item = occupied[id];
  return {
    id, size: id.startsWith("P") ? "Pocket-size" : "Medium-size",
    status: item ? "occupied" : "available",
    sensor: id === "P-06" ? "needs_attention" : id === "M-03" ? "disconnected" : "active",
    weightGrams: item?.[1] ?? 0, storedItem: item?.[0] ?? null,
    lastActivity: item?.[2] ?? "No recent activity",
  };
});

export function compartmentTotals(items: readonly Compartment[]) {
  return { available: items.filter((item) => item.status === "available").length, occupied: items.filter((item) => item.status === "occupied").length };
}

export const retrievalRecords: RetrievalRecord[] = [
  ["R-1087", "2026-09-09T12:44:00+08:00", "Angela Lim", "Brown coin purse", "P-04"],
  ["R-1086", "2026-09-09T11:18:00+08:00", "Paolo Cruz", "Black wallet", "P-07"],
  ["R-1085", "2026-09-08T16:32:00+08:00", "Maria Santos", "Blue water bottle", "M-02"],
  ["R-1084", "2026-09-08T14:06:00+08:00", "John Reyes", "Keychain", "P-06"],
  ["R-1083", "2026-09-07T15:51:00+08:00", "Ana Garcia", "Mobile phone", "P-03"],
  ["R-1082", "2026-09-07T10:23:00+08:00", "Carlo Mendoza", "Pencil case", "M-04"],
  ["R-1081", "2026-09-06T13:40:00+08:00", "Bea Torres", "Wristwatch", "P-02"],
  ["R-1080", "2026-09-05T09:16:00+08:00", "Miguel Ramos", "Eyeglass case", "M-01"],
].map(([id, timestamp, retriever, item, compartment]) => ({ id, timestamp, retriever, item, compartment: compartment as CompartmentId, status: "Retrieved", verification: "QR code verified" }));

export const unrecognizedCaptures: UnrecognizedCapture[] = [
  { id: "UC-001", title: "Unrecognized item", timestamp: "2026-10-04T10:42:00+08:00", source: "Raspberry Pi Camera", reason: "Item could not be identified confidently.", confidence: 34 },
  { id: "UC-002", title: "Unsupported category", timestamp: "2026-10-04T11:18:00+08:00", source: "Raspberry Pi Camera", reason: "Category is not represented in this prototype." },
  { id: "UC-003", title: "Low-confidence identification", timestamp: "2026-10-04T13:07:00+08:00", source: "Raspberry Pi Camera", reason: "The image did not provide enough detail.", confidence: 41 },
];

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
  return ["Retrieval ID,Date and Time,Retriever,Item,Compartment,Status", ...records.map((record) =>
    [record.id, formatManilaDate(record.timestamp), record.retriever, record.item, record.compartment, record.status].map(quote).join(",")
  )].join("\r\n");
}
