import Image from "next/image";

export default function ImagePairPreview({ front, back }: { front: string; back: string }) {
  return <section className="kiosk-card p-4"><h2 className="mb-2 text-lg font-bold">Captured item</h2><div className="grid grid-cols-2 gap-3">{[[front, "Side 1"], [back, "Side 2"]].map(([url, label]) => <div key={label} className="min-w-0"><p className="mb-1 text-sm font-semibold text-[#0b474f]">{label}</p><div className="relative overflow-hidden rounded-lg bg-[#e9eeee]" style={{ height: "clamp(180px, 28vh, 320px)" }}><Image src={url} alt={`${label} of the selected found item`} fill unoptimized sizes="(max-width: 900px) 45vw, 300px" className="object-contain" /></div></div>)}</div></section>;
}
