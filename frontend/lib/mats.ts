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
export function matSpec(p: { category: string; CNOMBREPRODUCTO: string; variant?: { options: Record<string, string> } | null }): MatSpec | null {
  if (!p.variant && !(p.category === "R_NW" && /TAPETE/i.test(p.CNOMBREPRODUCTO))) return null;
  const widthFt = parseInt(p.variant?.options.Ancho ?? "") || 4;
  const forAnimals = !/ESTANDAR/i.test(p.CNOMBREPRODUCTO); // the "estándar" mats are for people (gyms)
  return { widthFt, beds: forAnimals && widthFt === 4, nails: forAnimals && widthFt === 4 };
}
