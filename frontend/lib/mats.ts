// Every mat is 6 ft long; the width (1, 2 or 4 ft) says its use (user, 2026-10-15).
const FOOT_M = 0.3048;
export const MAT_LENGTH_FT = 6;
// Invoices bill 6 nails per 4 × 6 mat on most jobs (checked 2026-10-15); the installer confirms on site.
export const NAILS_PER_MAT = 6;

// Whole mats of widthFt × 6 ft to cover a length × width floor, laid in whichever direction needs fewer.
export function matsForArea(length: number, width: number, widthFt = 4) {
  if (!(length > 0 && width > 0)) return 0;
  const [w, l] = [widthFt * FOOT_M, MAT_LENGTH_FT * FOOT_M];
  const lay = (a: number, b: number) => Math.ceil(a / w - 1e-9) * Math.ceil(b / l - 1e-9);
  return Math.min(lay(length, width), lay(width, length));
}

export interface MatSpec {
  widthFt: number;
  beds: boolean; // one mat per bed: full-width animal mats
  nails: boolean; // 6 nails per mat: only checked on 4 ft mats
}

// What the calculator needs for a mat's page; null for anything that isn't a mat.
export function matSpec(p: { category: string; CNOMBREPRODUCTO: string; special_order?: boolean; variant?: { options: Record<string, string> } | null }): MatSpec | null {
  if (p.special_order) return null; // no standard size to calculate with
  if (!p.variant && !(p.category === "R_NW" && /TAPETE/i.test(p.CNOMBREPRODUCTO))) return null;
  const widthFt = parseInt(p.variant?.options.Ancho ?? "") || 4;
  const forAnimals = !/ESTANDAR/i.test(p.CNOMBREPRODUCTO); // the "estándar" mats are for people (gyms)
  return { widthFt, beds: forAnimals && widthFt === 4, nails: forAnimals && widthFt === 4 };
}

export interface MatLayer {
  label?: string;
  text: string;
  mm: number;
}

export type MatTop = "pebble" | "diamond" | "hexagon" | "dome" | "groove" | "cones" | "tee" | "ameba" | "perforated" | "flat";
export type MatBottom = "ripple" | "deepRipple" | "wideGroove" | "studs" | "cones" | "domes" | "pebble" | "arches" | "flat";

export interface MatSheet {
  uses: string[];
  layers: MatLayer[];
  top: MatTop;
  bottom: MatBottom;
  size: string | null;
  body: string; // the description without the uses line, now shown in the banner
}

const USES_LINE = /^(?:Dónde se usa|Uso):\s*(.+)\n*/m;

const line = (text: string, label: string) => text.match(new RegExp(`^${label}:\\s*(.+)$`, "m"))?.[1];

// 3/4" (19 mm), 3/4" a 1" (19 a 25 mm), 5 cm (2"), 3 mm (1/8"): the largest metric size.
function layer(value: string | undefined, label?: string): MatLayer[] {
  if (!value) return [];
  const text = value.split(",")[0];
  const m = text.match(/(\d+(?:\.\d+)?) (mm|cm)/) ?? [];
  const mm = text.match(/(\d+(?:\.\d+)?) mm\)/)?.[1] ?? (m[1] && Number(m[1]) * (m[2] === "cm" ? 10 : 1));
  return mm ? [{ label, text, mm: Number(mm) }] : [];
}

const pick = <T,>(value: string | undefined, rules: [RegExp, T][], otherwise: T) =>
  rules.find(([re]) => re.test(value ?? ""))?.[1] ?? otherwise;

const TOPS: [RegExp, MatTop][] = [
  [/perforad/i, "perforated"], [/diamante/i, "diamond"], [/hexagon/i, "hexagon"], [/abombad/i, "dome"],
  [/conos/i, "cones"], [/ranurad/i, "groove"], [/guijarro/i, "pebble"], [/ameba/i, "ameba"], [/\bT\b/, "tee"],
];
const BOTTOMS: [RegExp, MatBottom][] = [
  [/diagonal/i, "deepRipple"], [/ancha/i, "wideGroove"], [/ranura/i, "ripple"], [/tacos/i, "studs"], [/conos/i, "cones"],
  [/abombad/i, "domes"], [/guijarro/i, "pebble"], [/progresiva/i, "arches"],
];

// The Animat pages' spec banner, read from the staff-editable description so it can't drift from it.
// null for anything else, or when the description says none of it.
export function matSheet(text: string): MatSheet | null {
  if (!/Animat/.test(text)) return null;
  const uses = (text.match(USES_LINE)?.[1] ?? "")
    .split(/\.\s|,\s(?:en|sobre)\s/)[0] // the list, not the remarks after it
    .replace(/\.$/, "")
    .replace(/^[^:]*:\s*/, "")
    .split(/,\s*|\s+y\s+(?!salida)/) // "entradas y salidas" is one place
    .filter(Boolean)
    .map((u) => u[0].toUpperCase() + u.slice(1));
  const layers = [...layer(line(text, "Cubierta"), "Cubierta"), ...layer(line(text, "Espuma"), "Espuma"), ...layer(line(text, "Espesor"))];
  // A digit first: "Colchón de látex…" opens a sentence, "Colchón: 1.80 × 1.00 m" gives a size.
  const size = (text.match(/(?:Medida|Rollo|Colchón):?\s+(\d[^:,\n]*)/) ?? text.match(/^Espuma:[^,]*,\s*(.+)$/m))?.[1].replace(/\.$/, "") ?? null;
  if (!uses.length && !layers.length) return null;
  const top = pick(line(text, "Superficie"), TOPS, "flat");
  const bottom = pick(line(text, "Parte inferior"), BOTTOMS, "flat");
  return { uses, layers, top, bottom, size, body: text.replace(USES_LINE, "").trim() };
}
