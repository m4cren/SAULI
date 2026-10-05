"use client";

import Image from "next/image";
import Icon from "@/app/components/Icon";
import { useKiosk } from "../_hooks/useKioskFlow";
import type { ImageKind } from "../_types/kiosk";

export default function ImageDropzone({ kind, title, hint, qr = false }: { kind: ImageKind; title: string; hint: string; qr?: boolean }) {
  const { state, selectFile } = useKiosk();
  const url = state.images[kind];
  return <div className="flex min-h-[330px] items-stretch rounded-2xl border border-[#d3d7d7] bg-[#e8eeee] p-4 sm:min-h-[400px] sm:p-6">
    <label onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); const file = event.dataTransfer.files[0]; if (file) selectFile(kind, file); }} className="relative flex min-h-[300px] w-full cursor-pointer flex-col items-center justify-center overflow-hidden rounded-xl border border-dashed border-[#1f6370] bg-white px-5 text-center focus-within:outline-3 focus-within:outline-offset-2 focus-within:outline-[#0b474f]">
      {url ? <><Image src={url} alt={`${kind === "qr" ? "Selected QR" : kind === "front" ? "Selected side 1" : "Selected side 2"} image preview`} fill unoptimized sizes="(max-width: 900px) 90vw, 600px" className="object-contain p-3" /><span className="absolute bottom-3 rounded-md bg-white/95 px-3 py-1 text-sm font-semibold text-[#0b474f]">Click or drop to replace image</span></> : <><span className="mb-5 flex size-20 items-center justify-center rounded-full bg-white text-[#0b474f] shadow-md">{qr ? <span className="text-3xl font-bold">QR</span> : <Icon name="camera" size={40} />}</span><strong className="text-xl text-[#092a2f] sm:text-2xl">{title}</strong><span className="mt-1 text-sm text-[#333] sm:text-base">{hint}</span><span className="mt-5 rounded-md border border-[#0b474f] px-4 py-2 text-sm font-semibold text-[#0b474f]">{qr ? "Upload QR image" : "Choose or drop image"}</span></>}
      <input aria-label={qr ? "Upload QR image" : `Upload ${kind === "front" ? "side 1" : "side 2"} image`} type="file" accept="image/png,image/jpeg,image/webp,.png,.jpg,.jpeg,.webp" onChange={(event) => { const file = event.target.files?.[0]; if (file) selectFile(kind, file); event.target.value = ""; }} className="sr-only" />
    </label>
  </div>;
}
