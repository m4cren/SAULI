import type { ReactNode } from "react";

export default function StatusCard({ icon, title, children }: { icon: ReactNode; title: string; children: ReactNode }) {
  return <div className="flex items-center gap-3 rounded-xl border border-[var(--sauli-border)] bg-white p-3"><div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-[#dcefeb] text-[var(--sauli-brand)]">{icon}</div><div><p className="text-sm font-semibold">{title}</p><p className="text-xs text-[var(--sauli-muted)]">{children}</p></div></div>;
}
