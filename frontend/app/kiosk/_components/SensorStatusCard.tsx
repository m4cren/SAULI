export default function SensorStatusCard({ title, detail, status = "waiting" }: { title: string; detail: string; status?: "waiting" | "success" }) {
  return <div role="status" className="flex items-center gap-3 rounded-xl border border-[#d4e3e4] bg-[#f4fbfa] p-2"><span className={`flex size-8 shrink-0 items-center justify-center rounded-full ${status === "success" ? "bg-[#d5eee6] text-[#209d71]" : "bg-[#d4f5ed] text-[#0b7778]"}`}>●</span><div><p className="text-sm font-bold">{title}</p><p className="text-sm text-[#53646c]">{detail}</p></div></div>;
}
