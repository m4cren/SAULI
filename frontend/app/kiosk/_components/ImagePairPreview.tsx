import Image from "next/image";

export default function ImagePairPreview({ front, back }: { front: string; back: string }) {
  return <section className="kiosk-card kiosk-image-pair flex-1 p-4"><h2 className="mb-2 text-lg font-bold">Captured item</h2><div className="kiosk-image-pair-grid grid grid-cols-2 gap-3">{[[front, "Side 1"], [back, "Side 2"]].map(([url, label]) => <div key={label} className="flex min-h-0 min-w-0 flex-col"><p className="mb-1 text-sm font-semibold text-[#0b474f]">{label}</p><div className="relative min-h-[150px] flex-1 overflow-hidden rounded-lg bg-[#e9eeee]"><Image src={url} alt={`${label} of the selected found item`} fill unoptimized sizes="(max-width: 900px) 45vw, 300px" className="object-contain" /></div></div>)}</div></section>;
}
