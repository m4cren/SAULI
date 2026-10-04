import type { ReactNode } from "react";
import { connection } from "next/server";
import AuthProvider from "@/providers/AuthProvider";

export default async function LoginLayout({ children }: { children: ReactNode }) {
  await connection();
  return <AuthProvider initialUser={null}>{children}</AuthProvider>;
}
