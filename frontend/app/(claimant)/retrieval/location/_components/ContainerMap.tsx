import { mediumCodes, pocketCodes } from "@/libs/storage/slots";

export default function ContainerMap({ highlightedCode }: { highlightedCode: string }) {
  const cell = (id: string) => <div key={id} className={`flex items-center justify-center ${id === highlightedCode ? "bg-[#0c6370] text-white" : "bg-[#eef1f1]"}`}>{id}</div>;
  return <figure className="sauli-card mt-2 p-3"><div role="img" aria-label={`SAULI cabinet map. ${highlightedCode} is highlighted.`} className="grid h-[243px] grid-cols-[1.05fr_1.05fr_.8fr] gap-1 border-[4px] border-[#0c6370] bg-[#0c6370] p-1 text-center text-[8px] font-bold text-[#113840]">
    <div className="flex min-w-0 flex-col bg-white"><div className="border-b-2 border-[#0c6370] py-1 text-[9px]">POCKET-SIZE</div><div className="grid flex-1 grid-cols-2 grid-rows-5 gap-px bg-[#9fb9bd]">{pocketCodes.map(cell)}</div></div>
    <div className="flex min-w-0 flex-col bg-white"><div className="border-b-2 border-[#0c6370] py-1 text-[9px]">MEDIUM-SIZE</div><div className="grid flex-1 grid-rows-5 gap-px bg-[#9fb9bd]">{mediumCodes.map(cell)}</div></div>
    <div className="flex min-w-0 flex-col bg-white"><div className="border-b-2 border-[#0c6370] py-1 text-[9px]">STATION</div><div className="flex flex-1 items-center justify-center border-b border-[#9fb9bd] bg-[#eef1f1]">CAMERA</div><div className="flex flex-1 items-center justify-center bg-[#eef1f1]">TOUCH<br />SCREEN</div></div></div>
    <figcaption className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[9px] font-semibold text-[#315760]"><span className="flex items-center gap-1"><span className="size-3 bg-[#0c6370]" />YOUR COMPARTMENT</span><span className="flex items-center gap-1"><span className="size-3 border border-[#9fb9bd] bg-[#eef1f1]" />OTHER COMPARTMENTS</span></figcaption></figure>;
}
