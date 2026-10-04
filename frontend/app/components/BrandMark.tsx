export default function BrandMark({ large = false }: { large?: boolean }) {
  return (
    <span aria-label="SAULI" className={`inline-block select-none font-black leading-none tracking-[-0.075em] text-black ${large ? "text-[42px]" : "text-[25px]"}`}>
      S<span className="text-[#147c78]">A</span>UL<span className="text-[#147c78]">I</span>
    </span>
  );
}
