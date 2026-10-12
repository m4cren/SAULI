"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createClient } from "@/libs/supabase/browser";
import AdminIcon from "./AdminIcon";

const links = [
  { href: "/admin", label: "Container Status", icon: "grid" },
  { href: "/admin/retrieval-logs", label: "Retrieval Logs", icon: "logs" },
  { href: "/admin/cctv-footage", label: "CCTV Footage", icon: "camera" },
] as const;

export default function AdminSidebar() {
  const pathname = usePathname();
  const router = useRouter();
  async function signOut() {
    await createClient().auth.signOut();
    router.replace("/auth/admin");
    router.refresh();
  }
  return <aside className="admin-sidebar">
    <div className="admin-brand" aria-label="SAULI Admin">
      <span className="admin-brand-frame" aria-hidden="true"><span className="admin-brand-word">SAULI</span><span className="admin-brand-caption">ADMIN</span></span>
    </div>
    <nav className="admin-nav" aria-label="Administration">
      {links.map((link) => <Link key={link.href} href={link.href} aria-current={pathname === link.href ? "page" : undefined} className={`admin-nav-link ${pathname === link.href ? "active" : ""}`}><AdminIcon name={link.icon} size={20} /><span>{link.label}</span></Link>)}
    </nav>
    <div className="admin-sidebar-status"><span className="admin-status-light" aria-hidden="true" /><div><strong>Container status</strong><small>Refreshes every four seconds</small></div></div>
    <button type="button" className="mt-4 rounded-lg border border-white/50 px-4 py-2 text-left text-sm text-white" onClick={() => void signOut()}>Sign out</button>
  </aside>;
}
