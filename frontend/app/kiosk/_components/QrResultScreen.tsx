"use client";

import Button from "@/app/components/Button";
import Icon from "@/app/components/Icon";
import { isSlotCode } from "@/libs/storage/slots";
import { useKiosk } from "../_hooks/useKioskFlow";

export default function QrResultScreen({ valid }: { valid: boolean }) {
  const kiosk = useKiosk();
  const retrieval = kiosk.state.validatedRetrieval;
  const supported = !valid || (retrieval != null && isSlotCode(retrieval.slot_code));
  const accepted = valid && supported;
  const code = kiosk.state.qrErrorCode;
  const failureTitle = !supported ? "Staff assistance needed" : code === "RETRIEVAL_QR_EXPIRED" ? "This QR has expired" : code === "RETRIEVAL_QR_ALREADY_USED" ? "This QR was already used" : code === "ITEM_NOT_AVAILABLE" || code === "STORAGE_POSITION_MISMATCH" ? "Item unavailable" : "QR code could not be verified";
  const section = retrieval?.section === "medium" ? "Medium-size" : "Pocket-size";
  return <div className="flex min-h-[calc(100dvh-100px)] items-center justify-center"><section className="kiosk-card flex w-full max-w-[740px] flex-col items-center gap-3 px-6 py-8 text-center">
    <span className={`kiosk-electronic ${accepted ? "" : "!border-red-300 !bg-red-50 !text-red-700"}`} aria-hidden="true"><Icon name={accepted ? "check" : "close"} size={46} /></span>
    <span className="kiosk-pill mt-4">{accepted ? "QR CODE VERIFIED" : "QR VERIFICATION FAILED"}</span>
    <h1 className="text-[clamp(26px,3vw,38px)] font-bold">{accepted ? `${section} door is unlocked` : failureTitle}</h1>
    <p className="text-base text-[#53646c]">{accepted ? "Access granted. Continue to view the highlighted storage position." : supported ? kiosk.state.error : `Position ${retrieval?.slot_code} is retired from the current cabinet.`}</p>
    {accepted && retrieval && <dl className="mt-2 grid w-full grid-cols-3 gap-2 text-left text-sm"><div className="kiosk-card p-3"><dt className="kiosk-muted">Item</dt><dd className="font-bold">{retrieval.item_summary}</dd></div><div className="kiosk-card p-3"><dt className="kiosk-muted">Position</dt><dd className="font-bold text-[#299f93]">{retrieval.slot_code}</dd></div><div className="kiosk-card p-3"><dt className="kiosk-muted">Door</dt><dd className="font-bold">{section}</dd></div></dl>}
    {accepted ? <Button type="button" onClick={kiosk.showItemLocation} className="kiosk-button kiosk-button-primary mt-3">Show item location →</Button> : supported ? <div className="mt-3 grid w-full gap-2"><Button type="button" onClick={kiosk.tryAnotherQr} className="kiosk-button-primary">Try another QR</Button><Button type="button" variant="outline" onClick={kiosk.reset}>Return to kiosk home</Button></div> : <Button type="button" variant="outline" onClick={kiosk.reset} className="mt-3 w-full">Return to kiosk home</Button>}
  </section></div>;
}
