import Image from "next/image";

export default function ImagePairPreview({ front, back }: { front: string; back: string }) {
  return <section className="rounded-2xl border border-[#d4d4d4] bg-white p-5"><h2 className="mb-4 text-lg font-semibold text-[#092a2f]">Captured item</h2><div className="grid grid-cols-2 gap-4">{[[front, "Side 1"], [back, "Side 2"]].map(([url, label]) => <div key={label}><p className="mb-1 text-xs font-semibold text-[#0b474f]">{label}</p><div className="relative h-[clamp(150px,29vh,250px)] overflow-hidden rounded-lg bg-[#e9eeee]"><Image src={url} alt={`${label} of the selected found item`} fill unoptimized sizes="(max-width: 900px) 45vw, 300px" className="object-contain" /></div></div>)}</div></section>;
}
