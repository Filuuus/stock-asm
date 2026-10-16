import { describe, expect, it } from "vitest";
import { matSpec, matsForArea } from "./mats";

const FT = 0.3048;

describe("matsForArea", () => {
  it("is 0 for an empty or missing floor size", () => {
    expect(matsForArea(0, 5)).toBe(0);
    expect(matsForArea(5, -1)).toBe(0);
    expect(matsForArea(NaN, 5)).toBe(0);
  });

  it("counts exact fits as whole mats, not one more for rounding", () => {
    expect(matsForArea(4 * FT, 6 * FT)).toBe(1);
    expect(matsForArea(8 * FT, 6 * FT)).toBe(2);
    expect(matsForArea(12 * FT, 12 * FT)).toBe(6);
  });

  it("ignores floating-point dust: five mats' length (9.144000000000002 m) is five mats", () => {
    expect(matsForArea(4 * FT, 5 * (6 * FT))).toBe(5);
  });

  it("rounds a partial mat up", () => {
    expect(matsForArea(4 * FT + 0.01, 6 * FT)).toBe(2);
  });

  it("lays the mats in whichever direction needs fewer", () => {
    // 12 x 4 ft: three mats across the 12 ft, or two lengthwise
    expect(matsForArea(12 * FT, 4 * FT)).toBe(2);
    expect(matsForArea(4 * FT, 12 * FT)).toBe(2);
  });

  it("uses the mat's own width", () => {
    expect(matsForArea(4 * FT, 6 * FT, 2)).toBe(2);
    expect(matsForArea(4 * FT, 6 * FT, 1)).toBe(4);
  });
});

describe("matSpec", () => {
  const mat = (CNOMBREPRODUCTO: string, variant: { options: Record<string, string> } | null = null) => ({
    category: "R_NW",
    CNOMBREPRODUCTO,
    variant,
  });

  it("is null for anything that is not a mat", () => {
    expect(matSpec({ category: "R", CNOMBREPRODUCTO: "PEZONERA", variant: null })).toBeNull();
    expect(matSpec({ category: "R_NW", CNOMBREPRODUCTO: "CLAVO ESPECIAL", variant: null })).toBeNull();
  });

  it("treats a 4 ft animal mat as one per bed, with nails", () => {
    expect(matSpec(mat("TAPETE PEBBLETOP 4 X 6"))).toEqual({ widthFt: 4, beds: true, nails: true });
  });

  it("reads the width from the variant's options", () => {
    expect(matSpec(mat("TAPETE PEBBLETOP", { options: { Ancho: "2 ft" } }))).toEqual({
      widthFt: 2,
      beds: false,
      nails: false,
    });
  });

  it("gives the people (estándar) mats no beds or nails", () => {
    expect(matSpec(mat("TAPETE ESTANDAR 4 X 6"))).toEqual({ widthFt: 4, beds: false, nails: false });
  });
});
