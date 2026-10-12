"use client";

import Button from "@/app/components/Button";
import Icon from "@/app/components/Icon";
import { useKiosk } from "../_hooks/useKioskFlow";

export default function QrResultScreen({ valid }: { valid: boolean }) {
  const kiosk = useKiosk();
  const retrieval = kiosk.state.validatedRetrieval;
  const code = kiosk.state.qrErrorCode;
  const failureTitle = code === "RETRIEVAL_QR_EXPIRED" ? "This QR has expired" :
    code === "RETRIEVAL_QR_ALREADY_USED" ? "This QR was already used" :
    code === "ITEM_NOT_AVAILABLE" || code === "STORAGE_POSITION_MISMATCH" ? "Item unavailable" :
    "QR code could not be verified";
  return <div className="flex min-h-[calc(100dvh-170px)] items-center justify-center"><section className="flex min-h-[430px] w-full max-w-[670px] flex-col items-center rounded-2xl border-2 border-[#d6d6d6] bg-white px-5 py-8 text-center sm:px-12">
    <div className={`flex size-20 items-center justify-center rounded-full ${valid ? "bg-[#d3e6e3] text-[#0b474f]" : "bg-[#f8e1e1] text-red-600"}`}><Icon name={valid ? "check" : "close"} size={44} /></div>
    <p className={`mt-3 text-xs font-bold uppercase tracking-[0.08em] ${valid ? "text-[#0b474f]" : "text-red-600"}`}>{valid ? "QR accepted" : "QR verification failed"}</p>
    <h1 className="mt-3 text-2xl font-semibold text-[#092a2f]">{valid ? "QR verified" : failureTitle}</h1>
    <p className="mt-1 text-sm text-[#444]">{valid ? "Door unlocked — simulation. Continue to see the exact storage position." : kiosk.state.error}</p>
    {valid && retrieval && <dl className="mt-6 grid w-full grid-cols-3 gap-2 text-left text-sm">
      <div className="rounded-lg border border-[#d5d5d5] p-3"><dt className="text-xs text-[#666]">Item</dt><dd className="font-semibold">{retrieval.item_summary}</dd></div>
      <div className="rounded-lg border border-[#d5d5d5] p-3"><dt className="text-xs text-[#666]">Position</dt><dd className="font-semibold">{retrieval.slot_code}</dd></div>
      <div className="rounded-lg border border-[#d5d5d5] p-3"><dt className="text-xs text-[#666]">Door</dt><dd className="font-semibold">{retrieval.section === "pocket" ? "Pocket-size" : "Medium-size"}</dd></div>
    </dl>}
    <div className="mt-6 grid w-full gap-2">{valid ? <Button type="button" onClick={kiosk.showItemLocation}>Show item location</Button> : <Button type="button" onClick={kiosk.tryAnotherQr}>Try another QR</Button>}<Button type="button" variant="outline" onClick={kiosk.reset}>Return to kiosk home</Button></div>
  </section></div>;
}
