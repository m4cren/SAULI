"use client";

import { useSyncExternalStore, type ReactNode } from "react";
import BrandFrame from "@/app/components/BrandFrame";

const desktopQuery = "(min-width: 1024px)";

function subscribe(onChange: () => void) {
  const media = window.matchMedia(desktopQuery);
  media.addEventListener("change", onChange);
  return () => media.removeEventListener("change", onChange);
}

function isDesktop() {
  return window.matchMedia(desktopQuery).matches;
}

export default function DesktopOnlyAdmin({ children }: { children: ReactNode }) {
  const desktop = useSyncExternalStore(subscribe, isDesktop, () => false);

  return <>
    <main className="flex min-h-dvh flex-col items-center justify-center bg-[var(--sauli-background)] px-6 text-center text-[#092a2f] lg:hidden">
      <BrandFrame />
      <h1 className="mt-8 text-2xl font-bold">Admin is available on desktop</h1>
      <p className="mt-3 max-w-sm text-base text-[#426165]">Open SAULI Admin on a desktop screen or widen this window to continue.</p>
    </main>
    {desktop && <div className="hidden lg:block">{children}</div>}
  </>;
}
