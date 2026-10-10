import type { SVGProps } from "react";

type Name = "grid" | "logs" | "camera" | "check" | "box" | "door" | "computer" | "chip" | "display" | "light" | "download" | "search" | "play" | "pause" | "volume" | "mute" | "expand" | "close" | "chevronLeft" | "chevronRight" | "warning";

export default function AdminIcon({ name, size = 20, ...props }: SVGProps<SVGSVGElement> & { name: Name; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
    {name === "grid" && <><rect x="3" y="3" width="18" height="18" rx="2" /><path d="M3 9h18M3 15h18M9 3v18" /></>}
    {name === "logs" && <><path d="M7 3h12v16H7zM7 6H4v15h12v-2M10 8h6M10 12h6M10 16h4" /></>}
    {name === "camera" && <><path d="M3 8h4l2-3h6l2 3h4v12H3z" /><circle cx="12" cy="14" r="3" /></>}
    {name === "check" && <path d="m4 12 5 5L20 6" />}
    {name === "box" && <><path d="m12 2 9 5-9 5-9-5zM3 7v10l9 5 9-5V7M12 12v10" /></>}
    {name === "door" && <><rect x="5" y="2" width="14" height="20" rx="1" /><path d="M9 2v20M15 12h.01" /></>}
    {name === "computer" && <><rect x="3" y="4" width="18" height="13" rx="2" /><path d="M8 21h8M12 17v4" /></>}
    {name === "chip" && <><rect x="6" y="6" width="12" height="12" rx="1" /><path d="M9 9h6v6H9zM9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4" /></>}
    {name === "display" && <><rect x="2" y="4" width="20" height="15" rx="2" /><path d="M8 22h8M12 19v3" /></>}
    {name === "light" && <><path d="M9 17h6M10 20h4M12 2a7 7 0 0 0-4 13c1 .7 1 1.2 1 2h6c0-.8 0-1.3 1-2a7 7 0 0 0-4-13Z" /></>}
    {name === "download" && <><path d="M12 3v12m-4-4 4 4 4-4M4 17v4h16v-4" /></>}
    {name === "search" && <><circle cx="10" cy="10" r="7" /><path d="m15 15 6 6" /></>}
    {name === "play" && <path d="m8 4 12 8-12 8z" />}
    {name === "pause" && <><path d="M8 5v14M16 5v14" /></>}
    {name === "volume" && <><path d="M4 9h4l5-4v14l-5-4H4zM17 9a5 5 0 0 1 0 6M19 6a9 9 0 0 1 0 12" /></>}
    {name === "mute" && <><path d="M4 9h4l5-4v14l-5-4H4zM17 9l5 6M22 9l-5 6" /></>}
    {name === "expand" && <path d="M8 3H3v5M16 3h5v5M3 16v5h5M21 16v5h-5" />}
    {name === "close" && <path d="M5 5 19 19M19 5 5 19" />}
    {name === "chevronLeft" && <path d="m15 5-7 7 7 7" />}
    {name === "chevronRight" && <path d="m9 5 7 7-7 7" />}
    {name === "warning" && <><path d="m12 2 10 19H2zM12 9v5M12 18h.01" /></>}
  </svg>;
}
