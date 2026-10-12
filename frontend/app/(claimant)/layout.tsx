import type { ReactNode } from "react";
import { redirect } from "next/navigation";
import AuthProvider from "@/providers/AuthProvider";
import ClaimantProvider from "@/providers/ClaimantProvider";
import { createClient } from "@/libs/supabase/server";
import AppHeader from "@/app/components/AppHeader";
import BottomNavigation from "@/app/components/BottomNavigation";
import { isFacebookClaimant } from "@/libs/auth/claimant";
import MobilePageContainer from "@/app/components/MobilePageContainer";

export default async function ClaimantLayout({ children }: { children: ReactNode }) {
  const supabase = await createClient();
  const { data } = await supabase.auth.getUser();
  if (!data.user) redirect("/auth/login");
  if (!isFacebookClaimant(data.user)) redirect("/auth/login");

  return (
    <AuthProvider initialUser={data.user}>
      <ClaimantProvider userId={data.user.id}>
        <MobilePageContainer>
          <AppHeader />
          <div className="flex-1">{children}</div>
          <BottomNavigation />
        </MobilePageContainer>
      </ClaimantProvider>
    </AuthProvider>
  );
}
