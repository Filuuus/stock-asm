import { describe, expect, it } from "vitest";
import { parseDescription, specValue } from "./description";

describe("parseDescription", () => {
  const text =
    'Tapete de hule.\nMedida 4 × 6 pies (1.22 × 1.83 m).\n\n• Agarra bien\n• Dura más\n\nFicha técnica\nLínea: PebbleTop\nEspesor: 3/4" (19 mm)\n\n' +
    "Por qué ayuda: cuida las pezuñas.\n\nModelos (espuma · deformación)\nLift: 30 mm · 25 mm\nRise: 40 mm · 31 mm";

  it("turns each block into text, a list, specs or a labelled note", () => {
    const blocks = parseDescription(text);
    expect(blocks.map((b) => b.type)).toEqual(["text", "list", "specs", "note", "specs"]);
    expect(blocks[1]).toEqual({ type: "list", items: ["Agarra bien", "Dura más"] });
    expect(blocks[3]).toEqual({ type: "note", label: "Por qué ayuda", text: "cuida las pezuñas." });
    expect(blocks[4]).toMatchObject({ title: "Modelos (espuma · deformación)" });
    expect(specValue(blocks, "Espesor")).toBe('3/4" (19 mm)');
    expect(specValue(blocks, "Peso")).toBeNull();
  });

  it("keeps a bullet list that follows a heading line in the same block", () => {
    expect(parseDescription("Premezcla mineral\n• Uno\n• Dos").map((b) => b.type)).toEqual(["text", "list"]);
  });

  it("treats two labelled lines without a title as specs", () => {
    expect(parseDescription("Medida: 6 cm\nEspesor: 2 cm")[0].type).toBe("specs");
  });

  it("leaves ordinary sentences as text, even with a colon late in them", () => {
    expect(parseDescription("Medida 4 × 6 pies (1.22 × 1.83 m): para camas.")[0].type).toBe("text");
  });
});
