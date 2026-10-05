import BrandMark from "./BrandMark";

const leftGradient = "linear-gradient(90deg, #1c9e91 0%, #0b474f 100%)";
const rightGradient = "linear-gradient(90deg, #0b474f 0%, #1c9e91 100%)";

const corners = [
  { position: "left-0 top-0", gradient: leftGradient, shape: "polygon(0 0, 100% 0, 100% 13px, 13px 13px, 13px 100%, 0 100%)" },
  { position: "right-0 top-0", gradient: rightGradient, shape: "polygon(0 0, 100% 0, 100% 100%, calc(100% - 13px) 100%, calc(100% - 13px) 13px, 0 13px)" },
  { position: "bottom-0 left-0", gradient: leftGradient, shape: "polygon(0 0, 13px 0, 13px calc(100% - 13px), 100% calc(100% - 13px), 100% 100%, 0 100%)" },
  { position: "bottom-0 right-0", gradient: rightGradient, shape: "polygon(calc(100% - 13px) 0, 100% 0, 100% 100%, 0 100%, 0 calc(100% - 13px), calc(100% - 13px) calc(100% - 13px))" },
] as const;

export default function BrandFrame({ className = "" }: { className?: string }) {
  return <div className={`relative flex h-[106px] w-[200px] items-center justify-center ${className}`}>
    {corners.map(({ position, gradient, shape }) => <span key={position} aria-hidden="true" className={`absolute h-[30px] w-[58px] rounded-[2px] ${position}`} style={{ background: gradient, clipPath: shape }} />)}
    <BrandMark large />
  </div>;
}
