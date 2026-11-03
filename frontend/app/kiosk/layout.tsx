import type { ReactNode } from "react";
import { cookies } from "next/headers";
import { kioskCookieName, kioskSession } from "@/libs/api/kiosk-server";
import "./kiosk.css";

export default async function Layout({ children }: { children: ReactNode }) {
  const token = (await cookies()).get(kioskCookieName)?.value;
  if (!token || !(await kioskSession(token))) {
    return <main className="mx-auto flex min-h-screen max-w-xl flex-col justify-center gap-5 p-8 text-[#0B474F]">
      <h1 className="text-3xl font-bold">Kiosk registration required</h1>
      <p>This station must be enrolled and approved by a SAULI administrator before it can scan or store items.</p>
      <p>Ask the station operator to start the registered Pi controller, then reload this page.</p>
    </main>;
  }
  return children;
}
