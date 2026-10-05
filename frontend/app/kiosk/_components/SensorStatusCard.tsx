export default function SensorStatusCard({ title, detail, status = "waiting" }: { title: string; detail: string; status?: "waiting" | "success" }) {
  return <div role="status" className="mt-5 flex items-center gap-3 rounded-xl border border-[#d4d4d4] bg-white p-3"><span className={`flex size-6 shrink-0 items-center justify-center rounded-full ${status === "success" ? "bg-[#d5eee6] text-[#209d71]" : "bg-[#ffebc5] text-[#e7a32f]"}`}>●</span><div><p className="text-sm font-semibold">{title}</p><p className="text-xs text-[#555]">{detail}</p></div></div>;
}
