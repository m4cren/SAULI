"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import Icon from "./Icon";

export default function BottomNavigation() {
  const pathname = usePathname();
  const historyActive = pathname.startsWith("/history");
  return (
    <nav aria-label="Main navigation" className="sticky bottom-0 z-20 grid h-[74px] shrink-0 grid-cols-2 border-t border-[#e5e5e5] bg-white pb-[env(safe-area-inset-bottom)]">
      <Link href="/" aria-current={!historyActive ? "page" : undefined} className="client-nav-link"><span className="client-nav-icon"><Icon name="search" size={25} /></span>Search</Link>
      <Link href="/history" aria-current={historyActive ? "page" : undefined} className="client-nav-link"><span className="client-nav-icon"><Icon name="history" size={25} /></span>History</Link>
    </nav>
  );
}
