"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import BrandFrame from "@/app/components/BrandFrame";
import { createClient } from "@/libs/supabase/browser";

const ADMIN_USERNAME = "sauli-admin";
const ADMIN_AUTH_EMAIL = "sauli-admin@sauli.example";

export default function AdminLoginForm() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    if (username.trim() !== ADMIN_USERNAME || !password) {
      setError("Invalid administrator credentials.");
      return;
    }
    setLoading(true);
    try {
      const supabase = createClient();
      const result = await supabase.auth.signInWithPassword({ email: ADMIN_AUTH_EMAIL, password });
      if (result.error || !result.data.user || result.data.user.app_metadata?.sauli_role !== "admin" || result.data.user.app_metadata?.sauli_admin_username !== ADMIN_USERNAME) {
        if (result.data.session) await supabase.auth.signOut();
        throw new Error("Invalid administrator credentials.");
      }
      setPassword("");
      router.replace("/admin");
      router.refresh();
    } catch {
      setError("Invalid administrator credentials.");
      setLoading(false);
    }
  }

  return <main className="grid min-h-dvh w-full grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)] bg-[#f7f9f8] text-[#092a2f]">
    <section className="flex min-h-dvh flex-col justify-between bg-[linear-gradient(155deg,#07363d_0%,#0a535a_48%,#218f84_100%)] px-12 py-12 text-white">
      <p className="text-sm font-semibold tracking-[0.16em]">SAULI ADMIN</p>
      <div className="max-w-xl">
        <div className="mb-10 w-fit rounded-2xl bg-white px-7 py-5 shadow-xl"><BrandFrame /></div>
        <h1 className="text-4xl font-bold leading-tight">Administrator console</h1>
        <p className="mt-4 max-w-md text-lg leading-relaxed text-white/85">Monitor compartments and review SAULI activity from your desktop.</p>
      </div>
      <p className="text-sm text-white/70">Secure Automated Unit for Lost Item</p>
    </section>

    <section className="flex min-h-dvh items-center justify-center px-12 py-16">
      <div className="w-full max-w-[520px] rounded-2xl border border-[#d3d6d6] bg-white p-10 shadow-[0_18px_55px_rgba(9,42,47,0.08)]">
        <p className="text-sm font-semibold uppercase tracking-[0.12em] text-[#147c78]">Administrator access</p>
        <h2 className="mt-3 text-3xl font-bold">Sign in to SAULI</h2>
        <p className="mt-2 text-base text-[#426165]">Enter your admin account credentials to continue.</p>
        <form onSubmit={(event) => void submit(event)} className="mt-9 space-y-5">
          <div>
            <label className="mb-2 block text-sm font-semibold" htmlFor="admin-username">Username</label>
            <input id="admin-username" name="username" autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} required className="min-h-13 w-full rounded-lg border border-[#c9d2d3] px-4 text-base focus-visible:outline-2 focus-visible:outline-[#147c78]" />
          </div>
          <div>
            <label className="mb-2 block text-sm font-semibold" htmlFor="admin-password">Password</label>
            <input id="admin-password" name="password" type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required className="min-h-13 w-full rounded-lg border border-[#c9d2d3] px-4 text-base focus-visible:outline-2 focus-visible:outline-[#147c78]" />
          </div>
          {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
          <button type="submit" disabled={loading} className="min-h-13 w-full rounded-lg bg-[linear-gradient(180deg,#0b474f,#138d7d)] px-4 text-base font-semibold text-white disabled:opacity-60">{loading ? "Signing in…" : "Sign in"}</button>
        </form>
        <Link href="/auth/login" className="mt-7 block text-center text-sm font-medium text-[#0b474f] underline underline-offset-4">Back to user sign in</Link>
      </div>
    </section>
  </main>;
}
