export default function BrandMark({ large = false }: { large?: boolean }) {
  return (
    <span aria-label="SAULI" style={{ fontFamily: "var(--font-aldrich)", WebkitTextStroke: "0.04em #000" }} className={`inline-block select-none whitespace-nowrap font-bold leading-none tracking-[0.08em] text-black ${large ? "text-[42px]" : "text-[25px]"}`}>
      S<span style={{ WebkitTextStrokeColor: "#147c78" }} className="bg-gradient-to-r from-[#0b474f] to-[#1c9e91] bg-clip-text text-transparent">A</span>UL<span style={{ WebkitTextStrokeColor: "#147c78" }} className="bg-gradient-to-r from-[#0b474f] to-[#1c9e91] bg-clip-text text-transparent">I</span>
    </span>
  );
}
