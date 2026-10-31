"use client";

import BrandFrame from "@/app/components/BrandFrame";
import Icon from "@/app/components/Icon";
import { useKiosk } from "../_hooks/useKioskFlow";

export default function HomeActions() {
  const { startFound, startRetrieve } = useKiosk();
  const choices = [
    { title: "Scan a found item", detail: "Capture two sides, identify its size, then store it in an available position.", icon: "camera" as const, action: startFound },
    { title: "Retrieve my item", detail: "Scan the one-time QR code shown on your phone to open the correct door.", icon: "search" as const, action: startRetrieve },
  ];
  return <main className="kiosk-main flex min-h-dvh flex-col justify-center gap-5">
    <div><BrandFrame /><p className="mt-1 text-base text-[#254452]">Secure Automated Unit for Lost Item</p></div>
    <div><h1 className="text-[clamp(32px,4vw,48px)] font-bold leading-tight tracking-[-0.03em]">What would you like to do?</h1><p className="text-lg text-[#254452]">Choose one option to begin.</p></div>
    <div className="grid gap-4 md:grid-cols-2">{choices.map(({ title, detail, icon, action }) => <button key={title} type="button" onClick={action} className="kiosk-card flex min-h-[150px] items-center gap-5 p-5 text-left transition hover:border-[#299f93] focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-[#0b474f]">
      <span className="flex size-20 shrink-0 items-center justify-center rounded-2xl bg-[#ddf3f0] text-[#0b474f]"><Icon name={icon} size={43} /></span><span className="min-w-0 flex-1"><strong className="block text-[clamp(19px,2.4vw,29px)] leading-tight">{title}</strong><span className="mt-1 block text-[clamp(14px,1.5vw,17px)] leading-snug">{detail}</span></span><span aria-hidden="true" className="text-3xl text-[#0b474f]">→</span>
    </button>)}</div>
    <div className="kiosk-card flex flex-wrap gap-x-6 gap-y-2 px-5 py-3 text-sm"><p><span className="font-bold text-[#0b7778]">✓ Accepted:</span> safe personal items that fit a pocket-size or medium-size compartment.</p><p><span className="font-bold text-red-700">× Not accepted:</span> loose money, oversized, wet, perishable, or hazardous items.</p></div>
  </main>;
}
