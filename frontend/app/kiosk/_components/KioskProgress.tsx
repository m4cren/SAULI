import Icon from "@/app/components/Icon";

export default function KioskProgress({ flow, current }: { flow: "found" | "retrieve"; current: number }) {
  const labels = flow === "found" ? ["Capture", "Identify", "Store"] : ["Scan QR", "Locate", "Retrieve"];
  return <ol aria-label={`${flow === "found" ? "Found item" : "Retrieval"} progress`} className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm font-semibold text-[#b6b6b6] sm:text-base">
    {labels.map((label, index) => <li key={label} aria-current={index + 1 === current ? "step" : undefined} className={`flex items-center gap-2 ${index + 1 <= current ? "text-[#0b474f]" : ""}`}><span className={`flex size-7 items-center justify-center rounded-full border ${index + 1 === current ? "border-[#0b474f] bg-[#0b474f] text-white" : index + 1 < current ? "border-[#0b474f] bg-[#d4e8e5]" : "border-[#bbb]"}`}>{index + 1 < current ? <Icon name="check" size={16} /> : index + 1}</span>{label}</li>)}
  </ol>;
}
