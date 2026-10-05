import BrandMark from "@/app/components/BrandMark";
import DesktopTestControls from "./DesktopTestControls";

export default function KioskHeader() {
  return <header className="relative z-10 flex h-[74px] items-center justify-between border-b border-[#ddd] bg-white px-6 shadow-[0_2px_4px_rgba(0,0,0,0.09)] sm:px-14"><BrandMark /><DesktopTestControls /></header>;
}
