import { redirect } from "next/navigation";
import LoginPage from "./_components/LoginPage";
import { safeLocalPath } from "@/libs/auth/redirect";
import { isFacebookClaimant } from "@/libs/auth/claimant";
import { createClient } from "@/libs/supabase/server";

export default async function Page({
  searchParams,
}: {
  searchParams: Promise<{ next?: string | string[]; error?: string | string[] }>;
}) {
  const params = await searchParams;
  const next = safeLocalPath(params.next);
  const supabase = await createClient();
  const { data } = await supabase.auth.getUser();
  if (isFacebookClaimant(data.user)) redirect(next);

  const message =
    params.error === "denied"
      ? "Facebook sign-in was cancelled. You can try again when ready."
      : params.error === "callback"
        ? "We could not finish signing you in. Please try again."
        : undefined;
  return <LoginPage next={next} message={message} />;
}
