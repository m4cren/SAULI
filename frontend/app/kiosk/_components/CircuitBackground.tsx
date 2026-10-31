const tracks = [
  "M0 48h88l42-42h74",
  "M0 80h64l48-48h72",
  "M0 122h38l52-52h78",
  "M0 166h26l48-48v-36h66",
  "M0 686h28l58 58h72",
  "M0 742h46l60 60h90",
  "M0 805h24l75 75h105",
  "M0 862h70l32 32h68",
] as const;

const nodes = [
  [204, 6], [184, 32], [168, 70], [140, 82],
  [158, 744], [196, 802], [204, 880], [170, 894],
] as const;

export default function CircuitBackground() {
  return <div className="kiosk-circuit" aria-hidden="true">
    <svg viewBox="0 0 1440 900" preserveAspectRatio="none" className="h-full w-full" fill="none" xmlns="http://www.w3.org/2000/svg">
      {[false, true].map((mirror) => <g key={mirror ? "right" : "left"} transform={mirror ? "translate(1440 0) scale(-1 1)" : undefined}>
        <g stroke="#4cbdb8" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke">
          {(mirror ? tracks : [...tracks.slice(0, 3), ...tracks.slice(4)]).map((path) => <path key={path} d={path} />)}
        </g>
        <g fill="#60cfc8" stroke="#d8f4f0" strokeWidth="3" vectorEffect="non-scaling-stroke">
          {(mirror ? nodes : [...nodes.slice(0, 3), ...nodes.slice(4)]).map(([cx, cy]) => <circle key={`${cx}-${cy}`} cx={cx} cy={cy} r="5" />)}
        </g>
      </g>)}
    </svg>
  </div>;
}
