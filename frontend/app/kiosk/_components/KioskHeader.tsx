import BrandMark from "@/app/components/BrandMark";
import DesktopTestControls from "./DesktopTestControls";

export default function KioskHeader() {
  return <header className="relative z-20 flex h-[56px] items-center justify-between border-b border-[#d5e6e4] bg-white px-6 shadow-[0_2px_8px_rgba(5,55,63,0.09)] sm:px-12"><BrandMark />{process.env.NODE_ENV === "development" && <DesktopTestControls />}</header>;
}
