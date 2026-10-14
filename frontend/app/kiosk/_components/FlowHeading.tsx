import KioskProgress from "./KioskProgress";

export default function FlowHeading({ title, subtitle, flow, current, compact = false }: { title: string; subtitle: string; flow: "found" | "retrieve"; current: number; compact?: boolean }) {
  return <div className={`flex flex-wrap items-start justify-between gap-4 ${compact ? "mb-3 sm:flex-nowrap" : "mb-5"}`}><div className={compact ? "min-w-0" : undefined}><h1 className="text-[clamp(27px,3vw,36px)] font-semibold leading-tight tracking-[0.02em] text-[#092a2f]">{title}</h1><p className="mt-0.5 text-base leading-snug tracking-[0.03em] text-[#252525] sm:text-lg">{subtitle}</p></div><KioskProgress flow={flow} current={current} /></div>;
}
