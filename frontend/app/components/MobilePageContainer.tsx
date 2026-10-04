import type { ReactNode } from "react";

export default function MobilePageContainer({ children }: { children: ReactNode }) {
  return <div className="mx-auto flex min-h-dvh w-full max-w-[428px] flex-col overflow-x-clip bg-[var(--sauli-background)] shadow-[0_0_35px_rgba(0,0,0,0.08)]">{children}</div>;
}
