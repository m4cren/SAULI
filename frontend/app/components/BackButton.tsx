import Link from "next/link";
import Icon from "./Icon";

export default function BackButton({ href, children }: { href: string; children: string }) {
  return <Link href={href} className="inline-flex min-h-11 items-center gap-2 text-[15px] font-medium tracking-[0.11em] text-[#252525] focus-visible:outline-2 focus-visible:outline-[var(--sauli-brand)]"><Icon name="arrowLeft" size={19} />{children}</Link>;
}
