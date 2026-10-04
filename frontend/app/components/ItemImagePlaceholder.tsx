export default function ItemImagePlaceholder({ large = false }: { large?: boolean }) {
  return <div role="img" aria-label="Item image placeholder" className={`flex items-center justify-center rounded-[8px] bg-[#d9d9d9] text-center text-sm tracking-[0.04em] ${large ? "h-[195px] w-full" : "size-[93px] shrink-0"}`}>{large ? "IMAGE PLACEHOLDER" : "IMG"}</div>;
}
