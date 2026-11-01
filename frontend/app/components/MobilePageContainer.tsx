import type { ReactNode } from "react";

export default function MobilePageContainer({ children }: { children: ReactNode }) {
  return <div className="client-shell mx-auto flex min-h-dvh w-full max-w-[428px] flex-col overflow-x-clip shadow-[0_0_35px_rgba(0,0,0,0.08)]">{children}</div>;
}
