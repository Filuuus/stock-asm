import { MatBottom, MatLayer, MatSheet, MatTop } from "@/lib/mats";

const PX_PER_MM = 1.6;
const WIDTH = 168;

// One repeating tile of each surface: its width in px and how deep the rubber is cut away at x (0 to 1), in px.
type Tile = [number, (x: number) => number];
const round = (depth: number) => (x: number) => depth * (1 - Math.sin(Math.PI * x));
const cut = (share: number, depth: number) => (x: number) => (x < share ? depth : 0);

const TOPS: Record<MatTop, Tile> = {
  pebble: [10, round(2.5)],
  ameba: [18, (x) => 2.5 * (1 - Math.sin(Math.PI * x) ** 0.4)],
  diamond: [20, cut(0.28, 4)],
  hexagon: [32, (x) => (x < 0.12 ? 6 : x < 0.24 ? 3 : 0)],
  tee: [24, cut(0.5, 3)],
  dome: [28, round(4)],
  groove: [34, cut(0.16, 6)],
  // Pegs of two heights, tapering upward.
  cones: [34, (x) => Math.max(x < 0.5 ? 0 : 5, 14 * Math.min(1, 2.4 * Math.abs(((x * 2) % 1) - 0.5)))],
  perforated: [26, cut(0.42, Infinity)],
  flat: [WIDTH, () => 0],
};
const BOTTOMS: Record<MatBottom, Tile> = {
  ripple: [8, cut(0.45, 3)],
  deepRipple: [14, (x) => 6 * (1 - x)], // diagonal: a sawtooth, the grooves cut at an angle
  wideGroove: [28, cut(0.55, 4)],
  studs: [24, (x) => (x > 0.35 && x < 0.65 ? 0 : 6)],
  cones: [20, (x) => 22 * Math.min(1, 2.4 * Math.abs(x - 0.5))],
  domes: [46, round(12)],
  pebble: [10, round(2.5)],
  arches: [36, (x) => 10 * Math.sin(Math.PI * x)],
  flat: [WIDTH, () => 0],
};

// The mat's cross-section to scale: the top edge, then back along the bottom edge, sampled every half px.
function outline(top: MatTop, bottom: MatBottom, height: number, width: number) {
  const edge = ([tile, depth]: Tile, x: number) => Math.min(depth(((x % tile) + tile) % tile / tile), height);
  const points: string[] = [];
  for (let x = 0; x <= width; x += 0.5) points.push(`${x},${edge(TOPS[top], x).toFixed(1)}`);
  for (let x = width; x >= 0; x -= 0.5) points.push(`${x},${(height - Math.min(edge(BOTTOMS[bottom], x), height * 0.6)).toFixed(1)}`);
  return points.join(" ");
}

// To scale: a mat's own top and underside, or a mattress's cover over its foam.
export function Profile({ layers, top, bottom, width = WIDTH }: { layers: MatLayer[]; top: MatTop; bottom: MatBottom; width?: number }) {
  const heights = layers.map((l) => Math.max(l.mm * PX_PER_MM, 5));
  const total = heights.reduce((a, b) => a + b, 0);
  let y = 0;
  return (
    <svg
      width={width}
      height={total + 1}
      viewBox={`0 0 ${width} ${total + 1}`}
      role="img"
      aria-label={`Corte del producto: ${layers.map((l) => `${l.label ?? "espesor"} ${l.mm} mm`).join(", ")}`}
      className="shrink-0"
    >
      {layers.length === 1 ? (
        <polygon points={outline(top, bottom, total, width)} className="fill-slate-800" />
      ) : (
        layers.map((l, i) => {
          const rect = <rect key={l.text} y={y} width={width} height={heights[i]} className={i ? "fill-slate-300" : "fill-slate-800"} />;
          y += heights[i];
          return rect;
        })
      )}
    </svg>
  );
}

export default function MatSpecBanner({ sheet }: { sheet: MatSheet }) {
  const { uses, layers, size, top, bottom } = sheet;
  return (
    <div className="mb-6">
      {uses.length > 0 && (
        <div className="rounded-xl bg-slate-900 px-5 py-4 text-sm text-white sm:flex sm:gap-5">
          <p className="mb-2 shrink-0 font-semibold sm:mb-0">Adecuado para:</p>
          <ul className="flex flex-wrap gap-y-1">
            {uses.map((use, i) => (
              <li key={use} className={i < uses.length - 1 ? "mr-3 border-r border-white/40 pr-3" : ""}>
                {use}
              </li>
            ))}
          </ul>
        </div>
      )}
      {(layers.length > 0 || size) && (
        <div className="mt-4 flex flex-col gap-4 sm:flex-row sm:items-center sm:gap-8">
          <dl className="min-w-0 flex-1 divide-y divide-gray-200 text-sm">
            {layers.map((l) => (
              <div key={l.text} className="py-2 first:pt-0 last:pb-0">
                <dt className="inline font-semibold text-gray-900">{l.label ?? "Espesor"}: </dt>
                <dd className="inline text-gray-700">{l.text}</dd>
              </div>
            ))}
            {size && (
              <div className="py-2 first:pt-0 last:pb-0">
                <dt className="inline font-semibold text-gray-900">Medida: </dt>
                <dd className="inline text-gray-700">{size}</dd>
              </div>
            )}
          </dl>
          {layers.length > 0 && (
            <div className="flex items-center gap-4">
              <Profile layers={layers} top={top} bottom={bottom} />
              <div className="text-sm font-semibold text-gray-900">
                {layers.map((l) => (
                  <p key={l.text}>{l.mm} mm</p>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
      <p className="mt-3 text-xs text-gray-500">El diseño puede variar respecto a las imágenes.</p>
    </div>
  );
}
