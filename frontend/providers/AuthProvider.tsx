"use client";

import { createContext, useEffect, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/libs/supabase/browser";
import { safeLocalPath } from "@/libs/auth/redirect";
import type { AuthUser } from "@/libs/types/auth";

export interface AuthContextValue {
  user: AuthUser | null;
  isLoading: boolean;
  error: string | null;
  signInWithFacebook: (next?: string) => Promise<void>;
  signOut: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export default function AuthProvider({
  children,
  initialUser,
}: {
  children: ReactNode;
  initialUser: AuthUser | null;
}) {
  const [supabase] = useState(createClient);
  const [user, setUser] = useState<AuthUser | null>(initialUser);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();

  useEffect(() => {
    const { data } = supabase.auth.onAuthStateChange((_event, session) => {
      setUser(session?.user ?? null);
    });
    return () => data.subscription.unsubscribe();
  }, [supabase]);

  async function signInWithFacebook(next?: string) {
    setIsLoading(true);
    setError(null);
    const callback = new URL("/auth/callback", window.location.origin);
    callback.searchParams.set("next", safeLocalPath(next));
    try {
      const { error: authError } = await supabase.auth.signInWithOAuth({
        provider: "facebook",
        options: { redirectTo: callback.toString() },
      });
      if (authError) throw authError;
    } catch {
      setError("Facebook sign-in could not start. Please try again.");
      setIsLoading(false);
    }
  }

  async function signOut() {
    setIsLoading(true);
    setError(null);
    try {
      const { error: authError } = await supabase.auth.signOut();
      if (authError) throw authError;
      setUser(null);
      router.replace("/auth/login");
      router.refresh();
    } catch {
      setError("Could not sign out. Please try again.");
      setIsLoading(false);
    }
  }

  return (
    <AuthContext.Provider
      value={{ user, isLoading, error, signInWithFacebook, signOut }}
    >
      {children}
    </AuthContext.Provider>
  );
}
