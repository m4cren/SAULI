import type { ComponentPropsWithRef } from "react";

type ButtonVariant = "primary" | "outline" | "plain";

export default function Button({
  className = "",
  variant = "primary",
  ...props
}: ComponentPropsWithRef<"button"> & { variant?: ButtonVariant }) {
  const variants: Record<ButtonVariant, string> = {
    primary: "sauli-gradient text-white border-transparent",
    outline: "border-[var(--sauli-brand)] bg-transparent text-[var(--sauli-brand)] hover:bg-[#e2f1ee]",
    plain: "border-[var(--sauli-border)] bg-white text-[#161616] hover:bg-[#f6f6f6]",
  };
  return (
    <button
      {...props}
      className={`inline-flex min-h-12 items-center justify-center rounded-[8px] border px-5 py-3 text-[17px] font-semibold transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--sauli-brand)] disabled:cursor-not-allowed disabled:opacity-60 ${variants[variant]} ${className}`}
    />
  );
}
