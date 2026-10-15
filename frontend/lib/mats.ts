// A 4 × 6 ft rubber mat, in metres.
export const MAT_WIDTH_M = 4 * 0.3048;
export const MAT_LENGTH_M = 6 * 0.3048;
// Invoices bill 6 nails per mat on most mat jobs (checked 2026-10-15); the installer confirms on site.
export const NAILS_PER_MAT = 6;

// Whole mats to cover a length × width floor, laid in whichever direction needs fewer.
export function matsForArea(length: number, width: number) {
  if (!(length > 0 && width > 0)) return 0;
  const lay = (a: number, b: number) => Math.ceil(a / MAT_WIDTH_M - 1e-9) * Math.ceil(b / MAT_LENGTH_M - 1e-9);
  return Math.min(lay(length, width), lay(width, length));
}
