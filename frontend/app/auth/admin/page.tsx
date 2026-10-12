import { redirect } from "next/navigation";
import { createClient } from "@/libs/supabase/server";
import AdminLoginForm from "./AdminLoginForm";
import DesktopOnlyAdmin from "@/app/admin/_components/DesktopOnlyAdmin";

export default async function AdminLoginPage() {
  const { data } = await (await createClient()).auth.getUser();
  const user = data.user;
  const adminId = process.env.SAULI_ADMIN_USER_ID;
  if (adminId && user?.id === adminId && user.app_metadata?.sauli_role === "admin" && user.app_metadata?.sauli_admin_username === "sauli-admin") {
    redirect("/admin");
  }
  return <DesktopOnlyAdmin><AdminLoginForm /></DesktopOnlyAdmin>;
}
