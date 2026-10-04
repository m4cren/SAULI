"use client";

import { useState } from "react";
import BrandMark from "./BrandMark";
import { useAuth } from "@/hooks/useAuth";
import { avatarUrl, displayName } from "@/libs/types/auth";

export default function AppHeader() {
  const { user, isLoading, signOut } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const name = user ? displayName(user) : "SAULI user";
  const avatar = user ? avatarUrl(user) : null;

  return (
    <header className="sticky top-0 z-20 flex h-[74px] shrink-0 items-center justify-between bg-white px-[21px] shadow-[0_2px_4px_rgba(0,0,0,0.16)]">
      <BrandMark />
      <div className="relative">
        <button type="button" aria-label="Account menu" aria-expanded={menuOpen} onClick={() => setMenuOpen((value) => !value)} className="flex size-11 items-center justify-center rounded-full border border-[#e1e1e1] bg-white p-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--sauli-brand)]">
          {avatar ? <span role="img" aria-label={`${name}'s avatar`} className="size-9 rounded-full bg-cover bg-center" style={{ backgroundImage: `url(${JSON.stringify(avatar)})` }} /> : <span aria-hidden="true" className="flex size-9 items-center justify-center rounded-full bg-[#d7eae7] text-sm font-bold text-[var(--sauli-brand)]">{name.charAt(0).toUpperCase()}</span>}
        </button>
        {menuOpen && <div className="absolute right-0 top-12 z-30 w-48 rounded-xl border border-[var(--sauli-border)] bg-white p-2 shadow-lg"><p className="truncate px-3 py-2 text-sm font-medium">{name}</p><button type="button" disabled={isLoading} onClick={() => void signOut()} className="min-h-11 w-full rounded-lg px-3 text-left text-sm text-[var(--sauli-brand)] hover:bg-[#e8f3f1] focus-visible:outline-2 focus-visible:outline-[var(--sauli-brand)]">{isLoading ? "Signing out…" : "Sign out"}</button></div>}
      </div>
    </header>
  );
}
