import type { ReactNode } from "react";
import Link from "next/link";
import Icon from "./Icon";

type ClientHeroProps = {
  title?: string;
  subtitle?: string;
  eyebrow?: string;
  backHref?: string;
  backLabel?: string;
  align?: "left" | "center";
  icon?: ReactNode;
  children?: ReactNode;
  className?: string;
};

export default function ClientHero({
  title,
  subtitle,
  eyebrow,
  backHref,
  backLabel = "Back",
  align = "left",
  icon,
  children,
  className = "",
}: ClientHeroProps) {
  return (
    <section className={`client-hero ${align === "center" ? "client-hero-center" : ""} ${className}`}>
      <div className="client-hero-body">
        {backHref && <Link href={backHref} className="client-hero-back"><Icon name="arrowLeft" size={22} />{backLabel}</Link>}
        {icon && <div className="client-hero-icon" aria-hidden="true">{icon}</div>}
        {eyebrow && <p className="client-hero-eyebrow">{eyebrow}</p>}
        {title && <h1 className="client-hero-title">{title}</h1>}
        {subtitle && <p className="client-hero-subtitle">{subtitle}</p>}
        {children}
      </div>
    </section>
  );
}
