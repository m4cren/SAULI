"use client";

import Button from "@/app/components/Button";
import { useAuth } from "@/hooks/useAuth";

export default function FacebookLoginButton({ next }: { next: string }) {
  const { isLoading, error, signInWithFacebook } = useAuth();
  return (
    <div className="space-y-3">
      <Button
        type="button"
        variant="plain"
        className="facebook-button w-full gap-3 text-[16px] font-semibold"
        disabled={isLoading}
        onClick={() => void signInWithFacebook(next)}
      >
        <span aria-hidden="true" className="flex size-7 items-end justify-center rounded-full bg-white text-[24px] font-bold leading-none text-[#0866ff]">f</span>
        {isLoading ? "Connecting…" : "Continue with Facebook"}
      </Button>
      {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
    </div>
  );
}
