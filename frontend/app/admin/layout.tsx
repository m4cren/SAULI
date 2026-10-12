import type { ReactNode } from "react";
import { redirect } from "next/navigation";
import { createClient } from "@/libs/supabase/server";
import AdminSidebar from "./_components/AdminSidebar";
import DesktopOnlyAdmin from "./_components/DesktopOnlyAdmin";
import "./admin.css";

export default async function AdminLayout({ children }: { children: ReactNode }) {
  const { data } = await (await createClient()).auth.getUser();
  const user = data.user;
  const adminId = process.env.SAULI_ADMIN_USER_ID;
  if (!adminId || !user || user.id !== adminId || user.app_metadata?.sauli_role !== "admin" || user.app_metadata?.sauli_admin_username !== "sauli-admin") {
    redirect("/auth/admin");
  }
  return <DesktopOnlyAdmin><div className="admin-shell"><AdminSidebar /><main className="admin-main"><div className="admin-content">{children}</div></main></div></DesktopOnlyAdmin>;
}
