import type { SVGProps } from "react";

export type IconName = "search" | "history" | "arrowLeft" | "check" | "plus" | "camera" | "calendar" | "chevronDown" | "warning" | "clock" | "close" | "info" | "lightbulb";

export default function Icon({ name, size = 22, ...props }: SVGProps<SVGSVGElement> & { name: IconName; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" {...props}>
      {name === "search" && <><circle cx="10.7" cy="10.7" r="6.8" /><path d="m16 16 4.5 4.5" /></>}
      {name === "history" && <><path d="M3.7 10a8.5 8.5 0 1 1-.1 4.3" /><path d="M3.7 4.5V10h5.5" /><path d="M12 7.5v5l3.4 2" /></>}
      {name === "arrowLeft" && <><path d="m11.2 5-7 7 7 7" /><path d="M4.5 12h15" /></>}
      {name === "check" && <path d="m4.5 12 5 5 10-10" />}
      {name === "plus" && <><circle cx="12" cy="12" r="9" /><path d="M12 7v10M7 12h10" /></>}
      {name === "camera" && <><path d="M4 7h3l1.5-2h7L17 7h3v12H4z" /><circle cx="12" cy="12.5" r="3.2" /></>}
      {name === "calendar" && <><rect x="3.5" y="5" width="17" height="16" rx="2" /><path d="M7.5 3v4M16.5 3v4M3.5 9.5h17" /></>}
      {name === "chevronDown" && <path d="m5 9 7 7 7-7" />}
      {name === "warning" && <><path d="m12 3 10 18H2z" /><path d="M12 9v5M12 17.5h.01" /></>}
      {name === "clock" && <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>}
      {name === "close" && <path d="M5 5 19 19M19 5 5 19" />}
      {name === "info" && <><circle cx="12" cy="12" r="9" /><path d="M12 10.5v6M12 7.5h.01" /></>}
      {name === "lightbulb" && <><path d="M9 18h6M9.5 21h5M8.5 15.5c-1.8-1.2-2.8-3-2.8-5.2a6.3 6.3 0 0 1 12.6 0c0 2.2-1 4-2.8 5.2-.6.4-.9 1.2-.9 2H9.4c0-.8-.3-1.6-.9-2Z" /><path d="M12 1v2M3.8 4.5l1.5 1.5M20.2 4.5l-1.5 1.5M2.4 11h2M19.6 11h2" /></>}
    </svg>
  );
}
