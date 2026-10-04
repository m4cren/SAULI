const pixels = [
  "1111111001111", "1000001010001", "1011101010101", "1011101011101",
  "1011101000101", "1000001010101", "1111111011111", "0001000010010",
  "1110111011101", "1000100010001", "1011101010111", "1000100010101",
  "1110111011101",
];

export default function QrPlaceholder() {
  return (
    <div role="img" aria-label="Prototype QR pattern, not scannable" className="mx-auto grid size-[136px] grid-cols-[repeat(13,1fr)] gap-px bg-white p-1">
      {pixels.flatMap((row, rowIndex) => [...row].map((pixel, columnIndex) => <span key={`${rowIndex}-${columnIndex}`} className={pixel === "1" ? "bg-[#239f93]" : "bg-white"} />))}
    </div>
  );
}
