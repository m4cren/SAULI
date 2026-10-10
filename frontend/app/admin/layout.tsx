import type { ReactNode } from "react";
import AdminSidebar from "./_components/AdminSidebar";
import "./admin.css";

export default function AdminLayout({ children }: { children: ReactNode }) {
  return <div className="admin-shell"><AdminSidebar /><main className="admin-main"><div className="admin-content">{children}</div></main></div>;
}
