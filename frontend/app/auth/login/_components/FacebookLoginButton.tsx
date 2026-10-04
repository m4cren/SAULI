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
        className="w-full gap-3 text-sm font-medium"
        disabled={isLoading}
        onClick={() => void signInWithFacebook(next)}
      >
        <span aria-hidden="true" className="flex size-5 items-end justify-center rounded-full bg-[#1877f2] text-lg font-bold leading-none text-white">f</span>
        {isLoading ? "Connecting…" : "Continue with Facebook"}
      </Button>
      {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
    </div>
  );
}
