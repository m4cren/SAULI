import KioskProgress from "./KioskProgress";

export default function FlowHeading({ title, subtitle, flow, current, compact = false }: { title: string; subtitle: string; flow: "found" | "retrieve"; current: number; compact?: boolean }) {
  return <div className={`flex flex-wrap items-start justify-between gap-2 xl:gap-4 ${compact ? "mb-3" : "mb-4"}`}><div className="min-w-0"><h1 className="text-[clamp(27px,3vw,42px)] font-bold leading-tight tracking-[-0.025em] text-[#072e38]">{title}</h1><p className="mt-0.5 text-[clamp(15px,1.65vw,20px)] leading-snug text-[#254452]">{subtitle}</p></div><KioskProgress flow={flow} current={current} /></div>;
}
