import { isSlotCode, mediumCodes, pocketCodes } from "@/libs/storage/slots";

export default function ContainerMap({ highlightedCode }: { highlightedCode: string }) {
  if (!isSlotCode(highlightedCode)) {
    return <p role="alert" className="client-card mt-3 p-4 text-sm text-[#0b474f]">
      Position {highlightedCode} is retired from the current cabinet map. Ask SAULI staff for help locating this item.
    </p>;
  }

  const cell = (code: string) => <div
    key={code}
    className={`flex min-h-12 items-center justify-center border border-[#a9c9cc] text-[11px] font-semibold ${code === highlightedCode ? "bg-gradient-to-b from-[#168f8d] to-[#07556a] text-white shadow-[0_0_0_2px_#52e5d1,0_0_12px_#34cbb7]" : "bg-[#f6fafb] text-[#1b3142]"}`}
  >{code === highlightedCode && <span aria-hidden="true" className="mr-1 text-sm">●</span>}{code}</div>;

  return <figure className="client-card mt-3 p-3 shadow-[0_10px_25px_rgba(5,81,86,0.07)]">
    <div role="img" aria-label={`SAULI cabinet map with eight pocket-size compartments, four medium-size compartments, and the station. ${highlightedCode} is highlighted.`} className="grid min-h-60 grid-cols-[1.18fr_.92fr_.72fr] gap-1 rounded-md border-[4px] border-[#086474] bg-[#086474] p-1">
      <div className="flex min-w-0 flex-col bg-white">
        <div className="border-b-2 border-[#086474] py-1 text-center text-[9px] font-bold text-[#112d42] sm:text-[10px]">POCKET-SIZE</div>
        <div className="grid flex-1 grid-cols-2" style={{ gridTemplateRows: `repeat(${Math.ceil(pocketCodes.length / 2)}, minmax(0, 1fr))` }}>{pocketCodes.map(cell)}</div>
      </div>
      <div className="flex min-w-0 flex-col bg-white">
        <div className="border-b-2 border-[#086474] py-1 text-center text-[9px] font-bold text-[#112d42] sm:text-[10px]">MEDIUM-SIZE</div>
        <div className="grid flex-1" style={{ gridTemplateRows: `repeat(${mediumCodes.length}, minmax(0, 1fr))` }}>{mediumCodes.map(cell)}</div>
      </div>
      <div className="flex min-w-0 flex-col bg-white text-center text-[9px] font-bold text-[#112d42]">
        <div className="border-b-2 border-[#086474] py-1">STATION</div>
        <div className="flex flex-1 items-center justify-center border-b border-[#a9c9cc] bg-[#f6fafb]">CAMERA</div>
        <div className="flex flex-1 items-center justify-center bg-[#f6fafb]">TOUCH<br />SCREEN</div>
      </div>
    </div>
    <figcaption className="mt-3 flex flex-wrap gap-x-4 gap-y-1 px-1 text-xs text-[#354b5d]">
      <span className="flex items-center gap-2"><span aria-hidden="true" className="size-3 rounded-sm bg-[#078e92]" />Your compartment</span>
      <span className="flex items-center gap-2"><span aria-hidden="true" className="size-3 rounded-sm border border-[#a9c9cc] bg-[#f6fafb]" />Other compartments</span>
    </figcaption>
  </figure>;
}
