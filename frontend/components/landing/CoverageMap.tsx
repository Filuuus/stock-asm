// Where the routes reach: grid cells that hold at least one client (from
// /api/profitability/coverage/), with a few towns for reference. Cells are
// about 11 km wide, so no single ranch can be told apart.

export type Coverage = { step: number; cells: [number, number][] };

const OFFICE = { name: "Tepatitlán", lat: 20.8211, lng: -102.7513 }; // the office, per its Maps listing
const TOWNS = [
  { name: "Arandas", lat: 20.706, lng: -102.346 },
  { name: "San Juan de los Lagos", lat: 21.247, lng: -102.331 },
  { name: "Lagos de Moreno", lat: 21.356, lng: -101.929 },
  { name: "Jalostotitlán", lat: 21.167, lng: -102.466 },
  { name: "San Miguel el Alto", lat: 21.026, lng: -102.405 },
  { name: "Yahualica", lat: 21.178, lng: -102.886 },
  { name: "Zapotlanejo", lat: 20.623, lng: -103.069 },
  { name: "Atotonilco el Alto", lat: 20.551, lng: -102.509 },
  { name: "Ocotlán", lat: 20.346, lng: -102.774 },
  { name: "Guadalajara", lat: 20.677, lng: -103.347 },
];

const PAD = 0.12; // degrees around everything drawn
const SCALE = 400; // svg units per degree of latitude

export default function CoverageMap({ coverage }: { coverage: Coverage }) {
  const { step, cells } = coverage;
  const places = [OFFICE, ...TOWNS];
  const lats = [...cells.flatMap(([lat]) => [lat, lat + step]), ...places.map((p) => p.lat)];
  const lngs = [...cells.flatMap(([, lng]) => [lng, lng + step]), ...places.map((p) => p.lng)];
  const north = Math.max(...lats) + PAD;
  const south = Math.min(...lats) - PAD;
  const west = Math.min(...lngs) - PAD;
  const east = Math.max(...lngs) + PAD + 0.45; // room for the labels right of the dots
  // A degree of longitude is shorter than one of latitude this far north.
  const kx = SCALE * Math.cos((((north + south) / 2) * Math.PI) / 180);
  const x = (lng: number) => (lng - west) * kx;
  const y = (lat: number) => (north - lat) * SCALE;

  return (
    <svg
      viewBox={`0 0 ${x(east)} ${y(south)}`}
      role="img"
      aria-label="Mapa de la zona que cubren nuestras rutas en Los Altos de Jalisco"
      className="h-auto w-full"
    >
      <rect width={x(east)} height={y(south)} className="fill-slate-100" rx={12} />
      {cells.map(([lat, lng]) => (
        <rect
          key={`${lat},${lng}`}
          x={x(lng)}
          y={y(lat + step)}
          width={step * kx}
          height={step * SCALE}
          className="fill-emerald-500/70 stroke-slate-100"
          strokeWidth={2}
        />
      ))}
      {TOWNS.map((t) => (
        <g key={t.name}>
          <circle cx={x(t.lng)} cy={y(t.lat)} r={5} className="fill-slate-700" />
          <text x={x(t.lng) + 9} y={y(t.lat) + 6} className="fill-slate-800 text-[17px] font-medium">
            {t.name}
          </text>
        </g>
      ))}
      <circle cx={x(OFFICE.lng)} cy={y(OFFICE.lat)} r={10} className="fill-white stroke-slate-900" strokeWidth={5} />
      <text x={x(OFFICE.lng) + 15} y={y(OFFICE.lat) + 7} className="fill-slate-900 text-[20px] font-bold">
        {OFFICE.name} (oficina)
      </text>
    </svg>
  );
}
