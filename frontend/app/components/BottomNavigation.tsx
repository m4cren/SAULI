"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import Icon from "./Icon";

export default function BottomNavigation() {
  const pathname = usePathname();
  const historyActive = pathname.startsWith("/history");
  return (
    <nav aria-label="Main navigation" className="sticky bottom-0 z-20 grid h-[74px] shrink-0 grid-cols-2 border-t border-[#e5e5e5] bg-white pb-[env(safe-area-inset-bottom)]">
      <Link href="/" aria-current={!historyActive ? "page" : undefined} className={`flex min-h-11 flex-col items-center justify-center gap-0.5 text-sm font-semibold tracking-[0.08em] focus-visible:outline-2 focus-visible:outline-[var(--sauli-brand)] ${historyActive ? "text-[#8e8e8e]" : "text-black"}`}><Icon name="search" size={23} />Search</Link>
      <Link href="/history" aria-current={historyActive ? "page" : undefined} className={`flex min-h-11 flex-col items-center justify-center gap-0.5 text-sm font-semibold tracking-[0.08em] focus-visible:outline-2 focus-visible:outline-[var(--sauli-brand)] ${historyActive ? "text-black" : "text-[#8e8e8e]"}`}><Icon name="history" size={23} />History</Link>
    </nav>
  );
}
