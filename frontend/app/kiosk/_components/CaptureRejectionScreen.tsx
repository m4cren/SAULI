"use client";

import Image from "next/image";
import Button from "@/app/components/Button";
import Icon from "@/app/components/Icon";
import { useKiosk } from "../_hooks/useKioskFlow";
import FlowHeading from "./FlowHeading";

export default function CaptureRejectionScreen({ reason }: { reason: "noItem" | "hazardousItem" | "looseMoney" }) {
  const kiosk = useKiosk();
  const noItem = reason === "noItem";
  const hazard = reason === "hazardousItem";
  const title = noItem ? "No item detected" : hazard ? "Potential safety risk detected" : "This item cannot be accepted";
  const subtitle = noItem ? "We could not find an item in the captured photo." : hazard ? "This item cannot be placed inside the SAULI container." : "Loose money is not supported by the SAULI container.";
  const photo = kiosk.state.images.front;
  return <><FlowHeading flow="found" current={1} title={title} subtitle={subtitle} />
    <div className="kiosk-grid"><section className={`kiosk-card relative flex min-h-[280px] items-center justify-center overflow-hidden p-3 ${hazard ? "border-red-300 bg-red-50" : "border-amber-300 bg-amber-50"}`}>
      <div className="relative min-h-[250px] w-full self-stretch overflow-hidden rounded-xl bg-[#e7eff0]">{photo && <Image src={photo} fill unoptimized alt="Captured item" sizes="(max-width:900px) 90vw, 600px" className="object-contain" />}
      <span className={`absolute left-3 top-3 rounded-full px-3 py-2 text-sm font-bold ${hazard ? "bg-red-100 text-red-800" : "bg-amber-100 text-amber-900"}`}>! {noItem ? "No item found" : hazard ? "Potentially hazardous" : "Restricted item"}</span></div>
    </section><section className="kiosk-card flex flex-col p-5"><Icon name="warning" size={55} className={`mx-auto ${hazard ? "text-red-700" : "text-amber-700"}`} /><h2 className="mt-3 text-center text-[clamp(20px,2vw,27px)] font-bold">{noItem ? "Place the item inside the frame" : hazard ? "Do not place it in the cabinet" : "Please surrender it to campus security"}</h2>
      <p className="mt-2 text-center text-base">{noItem ? "Make sure the entire item is visible before capturing again." : hazard ? "Avoid further handling, keep others away, and notify campus security." : "Money may be accepted only when it is inside a wallet, purse, or similar container."}</p>
      {!noItem && <p className="mt-3 text-center text-sm text-[#7a8991]">No item record was created and no storage door will open.</p>}
      <div className="mt-auto grid gap-2 pt-4">{!hazard && <Button type="button" onClick={kiosk.retakePhotos} className="kiosk-button kiosk-button-primary">Retake photo</Button>}<Button type="button" variant={hazard ? "primary" : "outline"} onClick={noItem ? kiosk.requestCancel : kiosk.reset} className={`kiosk-button ${hazard ? "kiosk-button-primary" : ""}`}>{noItem ? "Cancel" : "End session"}</Button></div>
    </section></div>
  </>;
}
