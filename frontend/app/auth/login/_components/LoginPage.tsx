"use client";

import BrandFrame from "@/app/components/BrandFrame";
import FacebookLoginButton from "./FacebookLoginButton";

export default function LoginPage({
  next,
  message,
}: {
  next: string;
  message?: string;
}) {
  return (
    <main className="client-login-shell mx-auto flex min-h-dvh w-full max-w-[428px] flex-col overflow-x-clip bg-white shadow-[0_0_35px_rgba(0,0,0,0.08)]">
      <section className="client-hero client-login-hero" aria-label="SAULI">
        <div className="relative z-10 flex h-full flex-col items-center justify-center gap-5">
          <div className="client-login-mark rounded-[24px] border border-white/65 bg-white/90 px-5 py-4 shadow-[0_0_35px_rgba(105,255,230,.3)]"><BrandFrame /></div>
          <div className="text-center text-white"><p className="text-[18px] font-semibold">Secure Automated Unit for Lost Item</p><p className="mt-1 text-sm text-[#defaf7]">Campus lost-and-found, made safer.</p></div>
        </div>
      </section>
      <div className="flex flex-1 flex-col px-7 pb-[max(25px,env(safe-area-inset-bottom))] pt-[min(7vh,58px)]">
        <section className="text-center">
          <h1 className="text-[30px] font-bold leading-tight tracking-[-.03em] text-[#0a3038]">Welcome to SAULI</h1>
          <p className="mt-2 text-[16px] leading-[1.45] text-[#5b6f7d]">Sign in to search, report, and securely retrieve your item.</p>
          {message && <p role="alert" className="mt-5 rounded-xl bg-amber-50 p-3 text-left text-sm text-amber-900">{message}</p>}
          <div className="mt-7"><FacebookLoginButton next={next} /></div>
        </section>
        <p className="mt-auto pt-10 text-center text-[12px] leading-[1.5] text-[#667685]">By continuing, you agree to SAULI&apos;s Terms and Privacy Policy.</p>
      </div>
    </main>
  );
}
