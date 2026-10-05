"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import BrandFrame from "@/app/components/BrandFrame";
import FacebookLoginButton from "./FacebookLoginButton";

export default function LoginPage({
  next,
  message,
}: {
  next: string;
  message?: string;
}) {
  const { user } = useAuth();
  const router = useRouter();
  useEffect(() => {
    if (user) router.replace(next);
  }, [user, next, router]);

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-[428px] flex-col bg-[var(--sauli-background)] px-8 pb-10 shadow-[0_0_35px_rgba(0,0,0,0.08)]">
      <BrandFrame className="mx-auto mt-[min(13vh,120px)]" />
      <div className="mt-auto pt-10">
        <p className="mb-5 text-[17px] tracking-[0.02em]">Secure Automated Unit for Lost Item</p>
        <section className="rounded-[12px] bg-white px-[30px] py-[60px] shadow-[0_3px_4px_rgba(0,0,0,0.16)]">
          <h1 className="text-[23px] font-semibold leading-tight">Welcome</h1>
          <p className="text-[15px] tracking-[0.02em]">Sign in to search and retrieve an item.</p>
          {message && <p role="alert" className="mt-5 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">{message}</p>}
          <div className="mt-8"><FacebookLoginButton next={next} /></div>
        </section>
      </div>
      <p className="mt-[min(14vh,125px)] text-center text-xs text-[#4e4e4e]">By continuing, you agree to SAULI&apos;s Terms and Privacy Policy.</p>
    </main>
  );
}
