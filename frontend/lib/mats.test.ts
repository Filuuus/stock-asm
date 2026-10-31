import { describe, expect, it } from "vitest";
import { matSheet, matSpec, matsForArea } from "./mats";

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

describe("matSpec on special orders", () => {
  it("skips the calculator, even for one named TAPETE", () => {
    expect(matSpec({ category: "R_NW", CNOMBREPRODUCTO: "TAPETE NUEVO", special_order: true })).toBeNull();
  });
});

describe("matSheet", () => {
  it("reads uses, thickness and size, and takes the uses line out of the body", () => {
    const sheet = matSheet(
      'Tapete (Animat).\n\nMedida 4 × 6 pies (1.22 × 1.83 m): para camas.\n\nFicha técnica\nEspesor: 3/4" (19 mm)\n\n' +
        "Dónde se usa: corrales de espera, salas de ordeño y pasarelas. Va bien de pie.\n\nFin.",
    );
    expect(sheet?.uses).toEqual(["Corrales de espera", "Salas de ordeño", "Pasarelas"]);
    expect(sheet?.layers).toEqual([{ label: undefined, text: '3/4" (19 mm)', mm: 19 }]);
    expect(sheet?.size).toBe("4 × 6 pies (1.22 × 1.83 m)");
    expect(sheet?.body).not.toContain("corrales");
  });

  it("keeps entrance-and-exit lanes as one place and drops what follows the list", () => {
    expect(matSheet("Animat\nUso: mucho tráfico: cruces, carriles de entrada y salida.")?.uses).toEqual(["Cruces", "Carriles de entrada y salida"]);
    expect(matSheet("Animat\nDónde se usa: camas libres, en obra nueva o remodelación.")?.uses).toEqual(["Camas libres"]);
  });

  it("shows a mattress's cover over its foam, in mm", () => {
    const sheet = matSheet('Animat\nEspuma: 5 cm (2"), 1.80 × 1.00 m\nCubierta: 3 mm (1/8"), rollo de 50 m');
    expect(sheet?.layers.map((l) => [l.label, l.mm])).toEqual([["Cubierta", 3], ["Espuma", 50]]);
  });

  it("finds the size in a spec line, the foam line or a bullet, never in a sentence", () => {
    expect(matSheet("Colchón de látex (Animat).\nCubierta: 4 mm, rollo\nColchón: 1.80 × 1.00 m")?.size).toBe("1.80 × 1.00 m");
    expect(matSheet('Animat\nEspuma: 40 mm (1 1/2"), 1.78 × 1.00 m')?.size).toBe("1.78 × 1.00 m");
    expect(matSheet('Animat\nEspesor: 1" (25 mm)\n• Medida 1.80 × 1.00 m.')?.size).toBe("1.80 × 1.00 m");
  });

  it("reads the top and underside the drawing follows", () => {
    const of = (top: string, bottom: string) => {
      const sheet = matSheet(`Animat\nEspesor: 1" (25 mm)\nSuperficie: ${top}\nParte inferior: ${bottom}`);
      return [sheet?.top, sheet?.bottom];
    };
    expect(of("guijarro", "ranurada")).toEqual(["pebble", "ripple"]);
    expect(of("diamante con textura en relieve", "plana")).toEqual(["diamond", "flat"]);
    expect(of("T", "ranuras diagonales profundas")).toEqual(["tee", "deepRipple"]);
    expect(of("ameba", "ranuras anchas")).toEqual(["ameba", "wideGroove"]);
    expect(of("conos", "guijarro")).toEqual(["cones", "pebble"]);
    expect(of("guijarro", "conos")).toEqual(["pebble", "cones"]);
    expect(of("abombada", "con tacos")).toEqual(["dome", "studs"]);
    expect(of("lisa y antideslizante", "desconocida")).toEqual(["flat", "flat"]);
  });

  it("uses the top of a thickness range, and leaves other products alone", () => {
    expect(matSheet('Animat\nEspesor: 3/4" a 1" (19 a 25 mm)')?.layers[0].mm).toBe(25);
    expect(matSheet('Animat\nEspesor: 11/16" (17.5 mm)')?.layers[0].mm).toBe(17.5);
    expect(matSheet("Sustituto de leche.\nUso: becerras.")).toBeNull();
    expect(matSheet("Tapete Animat sin datos.")).toBeNull();
  });
});
