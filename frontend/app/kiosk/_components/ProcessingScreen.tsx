import Icon from "@/app/components/Icon";
import KioskProgress from "./KioskProgress";

export default function ProcessingScreen({ kind }: { kind: "identify" | "qr" | "storage" }) {
  const identify = kind === "identify";
  const storage = kind === "storage";
  return <div className="kiosk-center-screen"><section role="status" aria-live="polite" className="kiosk-card flex w-full max-w-[740px] flex-col items-center justify-center gap-3 px-6 py-8 text-center">
    {kind === "qr" && <KioskProgress flow="retrieve" current={2} />}
    <span className="kiosk-electronic mt-4" aria-hidden="true"><Icon name={identify ? "camera" : storage ? "check" : "search"} size={47} /></span>
    <span className="kiosk-pill mt-5">{identify ? "TWO SIDES RECEIVED" : storage ? "ITEM DETAILS CONFIRMED" : "CHECKING AUTHORIZATION"}</span>
    <h1 className="text-[clamp(26px,3vw,38px)] font-bold">{identify ? "Identifying the item…" : storage ? "Checking storage availability…" : "Verifying your QR code"}</h1>
    <p className="text-base text-[#53646c]">{identify ? "SAULI is preparing the item preview." : storage ? "SAULI is applying corrections and finding an available compartment." : "Please wait while SAULI confirms your retrieval access."}</p>
    {kind === "qr" && <div className="mt-3 flex flex-wrap justify-center gap-3 text-sm"><span>✓ QR detected</span><span>● Checking access</span><span className="text-[#8e9ba2]">○ Preparing location</span></div>}
    {storage && <div className="mt-3 grid gap-1 text-left text-sm"><span>✓ Item details updated</span><span>◌ Checking available compartments</span></div>}
  </section></div>;
}
